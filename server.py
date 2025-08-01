import json
import os
import ssl
from typing import Any, Dict
import logging

import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from flask import Flask, jsonify, request, render_template, flash, redirect, url_for
from flask_migrate import Migrate

from config import config
from models import db, ABVote, UserPreferences, SystemPrompt, AIPersona, ABTest, MessageProcessingJob
from services import (
    get_conversation_history,
    UserPreferencesService,
    PersonaManager,
    ChatService,
    SystemPromptManager,
    PersonaCreationService
)
from utils import setup_logger

# SSL and Environment Configuration
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context
load_dotenv()

# TODO logging.DEBUG to examine the 'ignore self reply' mode
logger = setup_logger(__name__)

# https://tools.slack.dev/python-slack-sdk/installation/#handling-tokens

# App Initialization
app = Flask(__name__)

# Database Configuration
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[config_name])

# Initialize database and migration
db.init_app(app)
migrate = Migrate(app, db)

# Initialize Slack client
slack_client = WebClient(token=os.environ["CHACHIBT_APP_BOT_AUTH_TOKEN"])


def handle_message(message: Dict[str, Any], client: WebClient) -> None:
    """Add message to database job queue for background processing (PythonAnywhere pattern)."""
    try:
        event_type = message.get("type", "unknown")
        user_id = message.get("user")
        channel_id = message.get("channel")
        message_ts = message.get("ts")
        thread_ts = message.get("thread_ts")
        message_text = message.get("text", "")
        
        if not all([user_id, channel_id, message_ts]):
            logger.error(f"Missing required fields in message: user={user_id}, channel={channel_id}, ts={message_ts}")
            return
        
        # Check if the message is from the bot itself BEFORE scheduling the job
        try:
            bot_user_id = client.auth_test()["user_id"]
            if user_id == bot_user_id:
                logger.info(f"HANDLE_MESSAGE: Ignoring bot's own message {channel_id}:{message_ts}")
                return
        except Exception as e:
            logger.error(f"Failed to get bot user ID: {e}")
            # Continue processing if we can't determine bot user ID
        
        # Serialize the full event payload for the background worker
        event_payload = json.dumps(message)
        
        # Add job to database queue
        job = MessageProcessingJob.add_job(
            event_type=event_type,
            user_id=user_id,
            channel_id=channel_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_text=message_text,
            event_payload=event_payload
        )

    except Exception as e:
        logger.error(f"JOB_ADD_ERROR: Failed to add job for message: {e}")


# Create tables if they don't exist (for local development)
# Skip during Flask CLI commands to avoid encoding issues
if not os.environ.get('FLASK_CLI_RUNNING'):
    with app.app_context():
        try:
            # Test database connection first using newer SQLAlchemy API
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            db.session.commit()
            db.create_all()
            logger.info("✅ Database tables created successfully")
            
            # Clean up old completed jobs on startup
            try:
                cleaned_count = MessageProcessingJob.cleanup_old_jobs(days=7)
                if cleaned_count > 0:
                    logger.info(f"🧹 Cleaned up {cleaned_count} old completed message processing jobs")
            except Exception as cleanup_error:
                logger.error(f"⚠️ Job cleanup failed: {cleanup_error}")
                
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            # Don't fail startup - let the app run and retry later

# Flask CLI Commands
@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    print("Database tables created.")

@app.cli.command()
def reset_db():
    """Reset the database (dangerous!)."""
    db.drop_all()
    db.create_all()
    print("Database reset complete.")

def load_json_view(file_name: str) -> Dict[str, Any]:
    """Load JSON view file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, "views", f"{file_name}.json")
    with open(json_path, "r") as file:
        return json.load(file)


def update_home_tab_with_user_data(user_id: str) -> Dict[str, Any]:
    """Load modal-based home tab and populate with user's current settings."""
    try:
        # Use the modal-based home tab view
        return update_modal_based_home_tab(user_id)
        
    except Exception as e:
        logger.error(f"Error building home tab for user {user_id}: {e}")
        # Fallback to basic modal-based view
        return load_json_view("app_home_modal_based")

def safe_publish_home_tab(user_id: str, view: Dict[str, Any] = None) -> bool:
    """
    Safely publish home tab updates with error handling.
    Returns True if successful, False otherwise.
    """
    try:
        if view is None:
            view = update_home_tab_with_user_data(user_id)
        
        # Publish the view directly without aggressive truncation
        # Slack supports up to 3000 characters for most text elements
        slack_client.views_publish(user_id=user_id, view=view)
        logger.info(f"Successfully published home tab for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to publish home tab for user {user_id}: {e}")
        
        # Try to send a fallback message
        try:
            slack_client.chat_postMessage(
                channel=user_id,
                text="⚠️ I'm having trouble updating your home tab, but you can still chat with me directly here!"
            )
        except Exception as fallback_e:
            logger.error(f"Even fallback message failed for user {user_id}: {fallback_e}")
        
        return False

# https://tools.slack.dev/node-slack-sdk/tutorials/local-development/
# https://api.slack.com/apis/events-api
@app.route("/event", methods=["POST"])
def slack_event_handler():
    """Handle Slack events with proper error handling via Flask error handlers."""
    # Get the JSON payload
    payload = request.get_json()
    logger.info(f"Received Slack event payload: {payload}")

    # Handle Slack URL verification
    if payload.get("type") == "url_verification":
        return jsonify({"challenge": payload["challenge"]})

    # Handle other events
    event = payload.get("event", {})
    event_type = event.get("type")
    
    if event_type == "app_home_opened":
        user_id = event.get("user")
        if user_id:
            safe_publish_home_tab(user_id)
    
    elif event_type in ["app_mention", "message"]:
        handle_message(event, slack_client)
    
    logger.info(f"Successfully processed Slack event type: {event_type}")
    
    # Return a 200 OK response to acknowledge receipt
    return jsonify({"status": "ok"})


@app.route("/process-job", methods=["POST"])
def process_job():
    """Process a message job (called by Always-On Task)."""
    try:
        data = request.get_json()
        job_id = data.get("job_id")
        event_payload = data.get("event_payload")
        
        if not job_id or not event_payload:
            return jsonify({
                "status": "error",
                "message": "Missing job_id or event_payload"
            }), 400
        
        # Parse the event data
        event_data = json.loads(event_payload) if isinstance(event_payload, str) else event_payload
        
        bot_user_id = slack_client.auth_test()["user_id"]
        user = event_data.get("user")
        
        # Note: Bot message check is now handled before scheduling in handle_message()
        
        channel_type = event_data.get("channel_type")
        channel = event_data.get("channel")
        thread_ts = event_data.get("thread_ts", event_data.get("ts"))
        message_ts = event_data.get("ts")
        event_type = event_data.get("type", "unknown")
        
        logger.info(f"PROCESS_JOB: Processing {event_type} event for message {message_ts} in channel {channel}")
        
        # Check if bot should respond
        tagged_in_parent = False
        if thread_ts:
            try:
                parent_message = slack_client.conversations_replies(
                    channel=channel, ts=thread_ts, limit=1
                )["messages"][0]
                tagged_in_parent = f"<@{bot_user_id}>" in parent_message.get("text", "")
            except Exception as e:
                logger.warning(f"Could not check parent message for job {job_id}: {e}")
        
        should_respond = (
            channel_type == "im"
            or f"<@{bot_user_id}>" in event_data.get("text", "")
            or tagged_in_parent
        )
        
        if not should_respond:
            logger.info(f"PROCESS_JOB: Skipping job {job_id} - bot not mentioned")
            return jsonify({
                "status": "success",
                "action": "skipped",
                "reason": "not_mentioned"
            })
        
        # Get conversation history
        conversation = get_conversation_history(slack_client, channel, thread_ts, bot_user_id)
        logger.info(f"PROCESS_JOB: Got conversation history with {len(conversation)} messages for job {job_id}")
        
        # Check if conversation already ends with assistant response (indicates late processing)
        if conversation and conversation[-1].get("role") == "assistant":
            logger.warning(f"PROCESS_JOB: Job {job_id} - conversation already ends with assistant response")
            logger.warning(f"PROCESS_JOB: This indicates the job was processed after bot already responded")
            logger.info(f"PROCESS_JOB: Skipping Claude API call for job {job_id} - no response needed")
            return jsonify({
                "status": "success",
                "action": "skipped",
                "reason": "conversation_already_complete"
            })
        
        # Use ChatService to handle the message based on user's mode
        logger.info(f"PROCESS_JOB: Starting ChatService request for job {job_id}")
        result: Dict | None = ChatService.handle_user_message(
            user_id=user,
            channel_id=channel,
            thread_ts=thread_ts,
            message_text=event_data.get("text", ""),
            conversation=conversation
        )
        
        if not result:
            logger.error(f"PROCESS_JOB: No result from ChatService for job {job_id}")
            return jsonify({
                "status": "success",
                "action": "skipped",
                "reason": "no_response_from_chat_service"
            })
        
        mode = result.get("mode")
        responses = result.get("responses", [])
        metadata = result.get("metadata", {})
        
        logger.info(f"PROCESS_JOB: ChatService returned mode: {mode}, {len(responses)} responses for job {job_id}")
        
        # Send responses via Slack
        messages_sent = []
        
        if mode == "chat_mode":
            # Single persona response
            if responses:
                response = responses[0]
                response_text = f"<@{user}> {response['text']}"
                
                if channel_type == "im":
                    result = slack_client.chat_postMessage(text=response_text, channel=channel)
                else:
                    result = slack_client.chat_postMessage(text=response_text, channel=channel, thread_ts=thread_ts)
                
                messages_sent.append({
                    "type": "chat_response",
                    "persona": response.get('persona_name'),
                    "message_ts": result.get("ts")
                })
                    
                logger.info(f"PROCESS_JOB: Sent chat mode response using persona: {response.get('persona_name')} for job {job_id}")
        
        elif mode == "ab_testing":
            # A/B testing responses
            if len(responses) >= 2:
                # Send intro message
                intro_text = f"<@{user}> {metadata.get('intro_message', 'Here are two responses:')}"
                
                if channel_type == "im":
                    intro_result = slack_client.chat_postMessage(text=intro_text, channel=channel)
                    
                    # Send response A
                    resp_a = slack_client.chat_postMessage(
                        channel=channel,
                        **responses[0]['slack_message']
                    )
                    
                    # Send response B  
                    resp_b = slack_client.chat_postMessage(
                        channel=channel,
                        **responses[1]['slack_message']
                    )
                    
                else:
                    intro_result = slack_client.chat_postMessage(text=intro_text, channel=channel, thread_ts=thread_ts)
                    
                    # Send response A in thread
                    resp_a = slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        **responses[0]['slack_message']
                    )
                    
                    # Send response B in thread
                    resp_b = slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        **responses[1]['slack_message']
                    )
                
                messages_sent.extend([
                    {"type": "intro", "message_ts": intro_result.get("ts")},
                    {"type": "response_a", "message_ts": resp_a.get("ts")},
                    {"type": "response_b", "message_ts": resp_b.get("ts")}
                ])
                
                logger.info(f"PROCESS_JOB: Sent A/B testing responses, test {metadata.get('ab_test_id')} for job {job_id}")
        
        return jsonify({
            "status": "success",
            "action": "processed",
            "mode": mode,
            "messages_sent": messages_sent,
            "job_id": job_id
        })
        
    except Exception as e:
        logger.error(f"PROCESS_JOB: Error processing job: {e}")
        import traceback
        logger.error(f"PROCESS_JOB: Traceback: {traceback.format_exc()}")
        
        return jsonify({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/interactive", methods=["POST"])
def handle_interactive_component():
    """Handle Slack interactive components with proper error handling via Flask error handlers."""
    payload = json.loads(request.form.get("payload"))
    logger.info(f"Received interactive payload type: {payload.get('type')}")
    
    # Extract action information
    actions = payload.get("actions", [])
    if not actions:
        return jsonify({"status": "ok"})
    
    action = actions[0]
    action_id = action.get("action_id")
    user_id = payload.get("user", {}).get("id")
    
    logger.info(f"Processing action: {action_id} for user: {user_id}")
    
    # Handle voting actions
    if action_id in ["vote_a", "vote_b"]:
        return handle_ab_vote(payload, action)
    
    # Handle mode selection
    elif action_id == "mode_selector":
        return handle_mode_selection(payload, action)
    
    # Handle A/B persona selections
    elif action_id in ["ab_persona_a_selector", "ab_persona_b_selector"]:
        return handle_ab_persona_selection(payload, action)
    
    # Handle chat persona selection
    elif action_id == "chat_persona_selector":
        return handle_chat_persona_selection(payload, action)
    
    # Handle settings save actions
    elif action_id == "save_ab_settings":
        return handle_save_ab_settings(payload)
    
    # Handle persona management actions
    elif action_id in ["view_personas", "create_persona", "view_analytics"]:
        return handle_persona_management(payload, action)
    
    # Handle modal-based editing actions
    elif action_id == "edit_chat_persona":
        return handle_edit_chat_persona_modal(payload, action)
    
    elif action_id == "configure_ab_testing":
        return handle_configure_ab_testing_modal(payload, action)
    
    elif action_id == "delete_persona":
        return handle_delete_persona(payload, action)
    
    # Handle inline persona editing actions (legacy)
    elif action_id == "save_chat_persona":
        return handle_save_chat_persona(payload)
    
    elif action_id == "save_ab_configuration":
        return handle_save_ab_configuration(payload)
    
    # Handle modal submissions
    elif payload.get("type") == "view_submission":
        return handle_modal_submission(payload)
    
    logger.warning(f"Unhandled action: {action_id}")
    return jsonify({"status": "ok"})


def handle_mode_selection(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle mode selection between A/B testing and chat mode."""
    try:
        user_id = payload.get("user", {}).get("id")
        selected_mode = action.get("selected_option", {}).get("value")
        
        if not user_id or not selected_mode:
            return jsonify({"error": "Missing data"}), 400
        
        # Update user's mode preference
        success = ChatService.set_user_mode(user_id, selected_mode)
        
        if success:
            # Update the home tab
            view = update_home_tab_with_user_data(user_id)
            safe_publish_home_tab(user_id, view)
            
            logger.info(f"Updated mode to {selected_mode} for user {user_id}")
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling mode selection: {e}")
        return jsonify({"error": "Failed to update mode"}), 500


def handle_ab_persona_selection(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle A/B persona selections and refresh home tab with selected persona data."""
    try:
        user_id = payload.get("user", {}).get("id")
        action_id = action.get("action_id")
        persona_id = action.get("selected_option", {}).get("value")
        
        if not all([user_id, action_id, persona_id]):
            return jsonify({"error": "Missing data"}), 400
        
        # Update the appropriate persona preference
        response_key = "response_a" if action_id == "ab_persona_a_selector" else "response_b"
        success = UserPreferencesService.update_ab_persona(user_id, response_key, int(persona_id))
        
        if success:
            # Refresh the home tab to populate fields with selected persona data
            view = update_home_tab_with_user_data(user_id)
            safe_publish_home_tab(user_id, view)
            
            logger.info(f"Updated {response_key} persona to {persona_id} for user {user_id}")
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling A/B persona selection: {e}")
        return jsonify({"error": "Failed to update persona"}), 500


def handle_chat_persona_selection(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle chat persona selection and refresh home tab with selected persona data."""
    try:
        user_id = payload.get("user", {}).get("id")
        persona_id = action.get("selected_option", {}).get("value")
        
        if not all([user_id, persona_id]):
            return jsonify({"error": "Missing data"}), 400
        
        # Get persona name for confirmation
        persona = PersonaManager.get_persona_by_id(int(persona_id), user_id)
        persona_name = persona['name'] if persona else f"Persona {persona_id}"
        
        # Update active persona
        success = PersonaManager.set_active_persona(user_id, int(persona_id))
        
        if success:
            # Refresh the home tab to populate fields with selected persona data
            view = update_home_tab_with_user_data(user_id)
            safe_publish_home_tab(user_id, view)
            
            # Send confirmation message with refresh instruction
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"✅ **Active persona changed to '{persona_name}'**"
            )
            
            logger.info(f"Updated active persona to {persona_id} for user {user_id}")
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling chat persona selection: {e}")
        return jsonify({"error": "Failed to update active persona"}), 500


def handle_save_ab_settings(payload: Dict[str, Any]) -> Any:
    """Handle saving A/B testing settings."""
    try:
        user_id = payload.get("user", {}).get("id")
        
        # Update home tab to show current settings
        view = update_home_tab_with_user_data(user_id)
        safe_publish_home_tab(user_id, view)
        
        # Send confirmation message
        slack_client.chat_postMessage(
            channel=user_id,  # DM the user
            text="✅ A/B testing settings saved! Your selected personas will be used for future comparisons."
        )
        
        logger.info(f"Saved A/B settings for user {user_id}")
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error saving A/B settings: {e}")
        return jsonify({"error": "Failed to save settings"}), 500


def handle_persona_management(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle persona management actions."""
    try:
        user_id = payload.get("user", {}).get("id")
        action_id = action.get("action_id")
        
        if action_id == "create_persona":
            # Open persona creation modal
            modal = load_json_view("create_persona_form")
            
            slack_client.views_open(
                trigger_id=payload.get("trigger_id"),
                view=modal
            )
            
        elif action_id == "view_personas":
            # Show personas list (placeholder for now)
            personas = PersonaManager.get_user_personas(user_id)
            
            text = "🎭 *Your Personas:*\n\n"
            for persona in personas:
                text += f"• **{persona['name']}** - {persona.get('description', 'No description')}\n"
                text += f"  Model: {persona['model']}, Temperature: {persona['temperature']}\n\n"
            
            if not personas:
                text += "No personas found. Create your first persona!"
            
            slack_client.chat_postMessage(
                channel=user_id,
                text=text
            )
            
        elif action_id == "view_analytics":
            # Show analytics (placeholder)
            slack_client.chat_postMessage(
                channel=user_id,
                text="📊 Analytics feature coming soon! This will show your persona usage statistics and A/B testing results."
            )
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling persona management: {e}")
        return jsonify({"error": "Failed to process action"}), 500


def handle_save_chat_persona(payload: Dict[str, Any]) -> Any:
    """Handle saving chat persona from inline form."""
    try:
        user_id = payload.get("user", {}).get("id")
        
        # Extract form values from home tab state
        values = payload.get("view", {}).get("state", {}).get("values", {})
        
        # Get selected persona ID from the selector
        selected_persona_id = values.get("chat_persona_selector", {}).get("chat_persona_selector", {}).get("selected_option", {}).get("value")
        
        # Extract form values
        persona_name = values.get("chat_persona_name", {}).get("chat_name_input", {}).get("value", "").strip()
        description = values.get("chat_persona_description", {}).get("chat_description_input", {}).get("value", "").strip()
        model = values.get("chat_ai_model", {}).get("chat_model_select", {}).get("selected_option", {}).get("value")
        temperature_str = values.get("chat_temperature", {}).get("chat_temperature_select", {}).get("selected_option", {}).get("value")
        system_prompt = values.get("chat_system_prompt", {}).get("chat_prompt_input", {}).get("value", "").strip()
        
        # Convert temperature to float
        try:
            temperature = float(temperature_str) if temperature_str else 0.7
        except (ValueError, TypeError):
            temperature = 0.7
        
        # Validate required fields
        if not all([persona_name, model, system_prompt]):
            slack_client.chat_postMessage(
                channel=user_id,
                text="❌ Please fill in all required fields: Persona Name, AI Model, and System Prompt."
            )
            return jsonify({"status": "ok"})
        
        if selected_persona_id:
            # Update existing persona
            persona_id = int(selected_persona_id)
            
            # Get current persona to check access and get current system prompt
            current_persona = PersonaManager.get_persona_by_id(persona_id, user_id)
            if not current_persona:
                slack_client.chat_postMessage(
                    channel=user_id,
                    text="❌ Persona not found or access denied."
                )
                return jsonify({"status": "ok"})
            
            # Handle system prompt updates
            current_prompt_id = current_persona.get('system_prompt_id')
            system_prompt_id = current_prompt_id
            
            # Check if prompt content has changed
            if current_prompt_id:
                current_prompt = SystemPromptManager.get_prompt_by_id(current_prompt_id, user_id)
                if current_prompt and current_prompt['content'].strip() != system_prompt.strip():
                    # Content changed, create a new system prompt
                    new_prompt = SystemPromptManager.create_prompt(
                        user_id=user_id,
                        title=f"{persona_name} Prompt (Updated)",
                        content=system_prompt,
                        description=f"Updated prompt for {persona_name} persona"
                    )
                    if new_prompt:
                        system_prompt_id = new_prompt['id']
                        logger.info(f"Created new prompt for updated persona '{persona_name}'")
                    else:
                        logger.warning(f"Failed to create new prompt for persona '{persona_name}', using existing")
            
            # Update the persona
            success = PersonaManager.update_persona(
                persona_id=persona_id,
                user_id=user_id,
                name=persona_name,
                model=model,
                temperature=temperature,
                system_prompt_id=system_prompt_id,
                description=description
            )
            
            if success:
                # Update home tab
                view_updated = update_home_tab_with_user_data(user_id)
                safe_publish_home_tab(user_id, view_updated)
                
                # Send confirmation
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=f"✅ Successfully updated persona '{persona_name}'!"
                )
                
                logger.info(f"Updated persona '{persona_name}' (ID: {persona_id}) for user {user_id}")
            else:
                slack_client.chat_postMessage(
                    channel=user_id,
                    text="❌ Failed to update persona. Name might already exist."
                )
        else:
            # Create new persona
            success, message, persona = PersonaCreationService.create_persona_with_prompt_handling(
                user_id=user_id,
                persona_name=persona_name,
                description=description,
                model=model,
                temperature=temperature,
                prompt_content=system_prompt,
                existing_prompt_id=None,
                save_new_prompt=True,
                new_prompt_title=f"{persona_name} Prompt"
            )
            
            if success:
                # Update home tab
                view_updated = update_home_tab_with_user_data(user_id)
                safe_publish_home_tab(user_id, view_updated)
                
                # Send confirmation
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=f"🎉 {message}"
                )
                
                logger.info(f"Created persona '{persona_name}' for user {user_id}")
            else:
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ {message}"
                )
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error saving chat persona: {e}")
        slack_client.chat_postMessage(
            channel=payload.get("user", {}).get("id"),
            text=f"❌ Unexpected error: {str(e)}"
        )
        return jsonify({"status": "ok"})


def handle_save_ab_configuration(payload: Dict[str, Any]) -> Any:
    """Handle saving A/B testing configuration from inline form."""
    try:
        user_id = payload.get("user", {}).get("id")
        
        # Extract form values from home tab state
        values = payload.get("view", {}).get("state", {}).get("values", {})
        
        # Persona A configuration
        persona_a_id = values.get("ab_persona_a_selector", {}).get("ab_persona_a_selector", {}).get("selected_option", {}).get("value")
        persona_a_name = values.get("ab_persona_a_name", {}).get("ab_a_name_input", {}).get("value", "").strip()
        persona_a_model = values.get("ab_a_model_select", {}).get("selected_option", {}).get("value")
        persona_a_temp_str = values.get("ab_a_temperature_select", {}).get("selected_option", {}).get("value")
        
        # Persona B configuration
        persona_b_id = values.get("ab_persona_b_selector", {}).get("ab_persona_b_selector", {}).get("selected_option", {}).get("value")
        persona_b_name = values.get("ab_persona_b_name", {}).get("ab_b_name_input", {}).get("value", "").strip()
        persona_b_model = values.get("ab_b_model_select", {}).get("selected_option", {}).get("value")
        persona_b_temp_str = values.get("ab_b_temperature_select", {}).get("selected_option", {}).get("value")
        
        # Convert temperatures to float
        try:
            persona_a_temp = float(persona_a_temp_str) if persona_a_temp_str else 0.7
        except (ValueError, TypeError):
            persona_a_temp = 0.7
            
        try:
            persona_b_temp = float(persona_b_temp_str) if persona_b_temp_str else 0.7
        except (ValueError, TypeError):
            persona_b_temp = 0.7
        
        # Validate required fields
        missing_fields = []
        if not persona_a_name:
            missing_fields.append("Persona A Name")
        if not persona_a_model:
            missing_fields.append("Persona A Model")
        if not persona_a_temp:
            missing_fields.append("Persona A Temperature")
        if not persona_b_name:
            missing_fields.append("Persona B Name")
        if not persona_b_model:
            missing_fields.append("Persona B Model")
        if not persona_b_temp:
            missing_fields.append("Persona B Temperature")
        
        if missing_fields:
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"❌ Please fill in all required fields: {', '.join(missing_fields)}"
            )
            return jsonify({"status": "ok"})
        
        # Update or create Persona A
        if persona_a_id:
            # Update existing persona A
            # Get current persona A to handle system prompt updates
            current_persona_a = PersonaManager.get_persona_by_id(int(persona_a_id), user_id)
            if current_persona_a:
                # Handle system prompt updates for Persona A
                current_prompt_id_a = current_persona_a.get('system_prompt_id')
                system_prompt_id_a = current_prompt_id_a
                
                if current_prompt_id_a:
                    current_prompt_a = SystemPromptManager.get_prompt_by_id(current_prompt_id_a, user_id)
                    if current_prompt_a and current_prompt_a['content'].strip() != persona_a_temp:
                        # Content changed, create a new system prompt
                        new_prompt_a = SystemPromptManager.create_prompt(
                            user_id=user_id,
                            title=f"{persona_a_name} A/B Prompt (Updated)",
                            content=persona_a_temp,
                            description=f"Updated A/B testing prompt for {persona_a_name}"
                        )
                        if new_prompt_a:
                            system_prompt_id_a = new_prompt_a['id']
                
                success_a = PersonaManager.update_persona(
                    persona_id=int(persona_a_id),
                    user_id=user_id,
                    name=persona_a_name,
                    model=persona_a_model,
                    temperature=persona_a_temp,
                    system_prompt_id=system_prompt_id_a,
                    description=f"A/B Testing Persona A"
                )
            else:
                success_a = False
        else:
            # Create new persona A
            success_a, message_a, persona_a = PersonaCreationService.create_persona_with_prompt_handling(
                user_id=user_id,
                persona_name=persona_a_name,
                description="A/B Testing Persona A",
                model=persona_a_model,
                temperature=persona_a_temp,
                prompt_content=persona_a_temp,
                existing_prompt_id=None,
                save_new_prompt=True,
                new_prompt_title=f"{persona_a_name} Prompt"
            )
            if success_a:
                persona_a_id = persona_a['id']
        
        # Update or create Persona B
        if persona_b_id:
            # Update existing persona B
            # Get current persona B to handle system prompt updates
            current_persona_b = PersonaManager.get_persona_by_id(int(persona_b_id), user_id)
            if current_persona_b:
                # Handle system prompt updates for Persona B
                current_prompt_id_b = current_persona_b.get('system_prompt_id')
                system_prompt_id_b = current_prompt_id_b
                
                if current_prompt_id_b:
                    current_prompt_b = SystemPromptManager.get_prompt_by_id(current_prompt_id_b, user_id)
                    if current_prompt_b and current_prompt_b['content'].strip() != persona_b_temp:
                        # Content changed, create a new system prompt
                        new_prompt_b = SystemPromptManager.create_prompt(
                            user_id=user_id,
                            title=f"{persona_b_name} A/B Prompt (Updated)",
                            content=persona_b_temp,
                            description=f"Updated A/B testing prompt for {persona_b_name}"
                        )
                        if new_prompt_b:
                            system_prompt_id_b = new_prompt_b['id']
                
                success_b = PersonaManager.update_persona(
                    persona_id=int(persona_b_id),
                    user_id=user_id,
                    name=persona_b_name,
                    model=persona_b_model,
                    temperature=persona_b_temp,
                    system_prompt_id=system_prompt_id_b,
                    description=f"A/B Testing Persona B"
                )
            else:
                success_b = False
        else:
            # Create new persona B
            success_b, message_b, persona_b = PersonaCreationService.create_persona_with_prompt_handling(
                user_id=user_id,
                persona_name=persona_b_name,
                description="A/B Testing Persona B",
                model=persona_b_model,
                temperature=persona_b_temp,
                prompt_content=persona_b_temp,
                existing_prompt_id=None,
                save_new_prompt=True,
                new_prompt_title=f"{persona_b_name} Prompt"
            )
            if success_b:
                persona_b_id = persona_b['id']
        
        # Update A/B testing preferences
        if persona_a_id:
            UserPreferencesService.update_ab_persona(user_id, "response_a", int(persona_a_id))
        if persona_b_id:
            UserPreferencesService.update_ab_persona(user_id, "response_b", int(persona_b_id))
        
        # Update home tab to show current settings
        view = update_home_tab_with_user_data(user_id)
        safe_publish_home_tab(user_id, view)
        
        # Send confirmation message
        slack_client.chat_postMessage(
            channel=user_id,
            text="✅ A/B testing configuration saved! Your personas are ready for side-by-side comparison."
        )
        
        logger.info(f"Saved A/B testing configuration for user {user_id}")
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error saving A/B testing configuration: {e}")
        slack_client.chat_postMessage(
            channel=payload.get("user", {}).get("id"),
            text=f"❌ Unexpected error: {str(e)}"
        )
        return jsonify({"status": "ok"})


def handle_modal_submission(payload: Dict[str, Any]) -> Any:
    """Handle modal form submissions."""
    try:
        view = payload.get("view", {})
        callback_id = view.get("callback_id")
        user_id = payload.get("user", {}).get("id")
        
        if callback_id == "create_persona":
            return handle_create_persona_submission(payload, user_id)
        elif callback_id == "edit_persona_modal":
            return handle_edit_persona_submission(payload, user_id)
        elif callback_id == "ab_config_modal":
            return handle_ab_config_submission(payload, user_id)
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling modal submission: {e}")
        return jsonify({"error": "Failed to process submission"}), 500


def handle_create_persona_submission(payload: Dict[str, Any], user_id: str) -> Any:
    """Handle persona creation form submission."""
    try:
        values = payload.get("view", {}).get("state", {}).get("values", {})
        
        # Extract form values
        persona_name = values.get("persona_name", {}).get("name_input", {}).get("value", "").strip()
        description = values.get("persona_description", {}).get("description_input", {}).get("value", "").strip()
        model = values.get("model_selection", {}).get("model_select", {}).get("selected_option", {}).get("value")
        temperature = float(values.get("temperature_section", {}).get("temperature_select", {}).get("selected_option", {}).get("value", "0.7"))
        
        # System prompt handling
        prompt_selection = values.get("system_prompt_selector", {}).get("prompt_select", {}).get("selected_option", {})
        prompt_content = values.get("system_prompt_content", {}).get("prompt_input", {}).get("value", "").strip()
        
        # Prompt saving options
        save_prompt_checked = values.get("save_prompt_options", {}).get("save_prompt_checkbox", {}).get("selected_options", [])
        save_new_prompt = len(save_prompt_checked) > 0
        new_prompt_title = values.get("new_prompt_title", {}).get("prompt_title_input", {}).get("value", "").strip()
        
        # Validate required fields
        if not all([persona_name, model, prompt_content]):
            return jsonify({
                "response_action": "errors",
                "errors": {
                    "persona_name": "Persona name is required" if not persona_name else "",
                    "model_selection": "Model selection is required" if not model else "",
                    "system_prompt_content": "System prompt content is required" if not prompt_content else ""
                }
            })
        
        # Handle existing prompt selection
        existing_prompt_id = None
        if prompt_selection and prompt_selection.get("value") != "new_prompt":
            try:
                existing_prompt_id = int(prompt_selection.get("value"))
            except (ValueError, TypeError):
                pass
        
        # Create persona using the creation service
        success, message, persona = PersonaCreationService.create_persona_with_prompt_handling(
            user_id=user_id,
            persona_name=persona_name,
            description=description,
            model=model,
            temperature=temperature,
            prompt_content=prompt_content,
            existing_prompt_id=existing_prompt_id,
            save_new_prompt=save_new_prompt,
            new_prompt_title=new_prompt_title if new_prompt_title else None
        )
        
        if success:
            # Update home tab
            view = update_home_tab_with_user_data(user_id)
            safe_publish_home_tab(user_id, view)
            
            # Send confirmation
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"🎉 {message}"
            )
            
            logger.info(f"Created persona '{persona_name}' for user {user_id}")
            
            return jsonify({"response_action": "clear"})
        else:
            return jsonify({
                "response_action": "errors", 
                "errors": {
                    "persona_name": message if "name" in message.lower() else "",
                    "system_prompt_content": message if "prompt" in message.lower() else "",
                    "general": message
                }
            })
        
    except Exception as e:
        logger.error(f"Error creating persona: {e}")
        return jsonify({
            "response_action": "errors",
            "errors": {
                "general": f"Unexpected error: {str(e)}"
            }
        })


def handle_edit_persona_submission(payload: Dict[str, Any], user_id: str) -> Any:
    """Handle edit persona form submission."""
    try:
        view = payload.get("view", {})
        private_metadata = json.loads(view.get("private_metadata", "{}"))
        persona_id = private_metadata.get("persona_id")
        
        if not persona_id:
            return jsonify({
                "response_action": "errors",
                "errors": {"general": "Invalid persona data"}
            })
        
        values = view.get("state", {}).get("values", {})
        
        # Extract form values
        persona_name = values.get("persona_name", {}).get("name_input", {}).get("value", "").strip()
        description = values.get("persona_description", {}).get("description_input", {}).get("value", "").strip()
        model = values.get("model_selection", {}).get("model_select", {}).get("selected_option", {}).get("value")
        temperature_str = values.get("temperature_section", {}).get("temperature_select", {}).get("selected_option", {}).get("value")
        system_prompt = values.get("system_prompt", {}).get("prompt_input", {}).get("value", "").strip()
        
        # Convert temperature to float
        try:
            temperature = float(temperature_str) if temperature_str else 0.7
        except (ValueError, TypeError):
            temperature = 0.7
        
        # Validate required fields
        if not all([persona_name, model, system_prompt]):
            return jsonify({
                "response_action": "errors",
                "errors": {
                    "persona_name": "Persona name is required" if not persona_name else "",
                    "model_selection": "Model selection is required" if not model else "",
                    "system_prompt": "System prompt is required" if not system_prompt else ""
                }
            })
        
        # Get current persona to handle system prompt updates
        current_persona = PersonaManager.get_persona_by_id(persona_id, user_id)
        if not current_persona:
            return jsonify({
                "response_action": "errors",
                "errors": {"general": "Persona not found or access denied"}
            })
        
        # Handle system prompt updates
        current_prompt_id = current_persona.get('system_prompt_id')
        system_prompt_id = current_prompt_id
        
        if current_prompt_id:
            current_prompt = SystemPromptManager.get_prompt_by_id(current_prompt_id, user_id)
            if current_prompt and current_prompt['content'].strip() != system_prompt.strip():
                # Content changed, create a new system prompt
                new_prompt = SystemPromptManager.create_prompt(
                    user_id=user_id,
                    title=f"{persona_name} Prompt (Updated)",
                    content=system_prompt,
                    description=f"Updated prompt for {persona_name} persona"
                )
                if new_prompt:
                    system_prompt_id = new_prompt['id']
        
        # Update the persona
        success = PersonaManager.update_persona(
            persona_id=persona_id,
            user_id=user_id,
            name=persona_name,
            model=model,
            temperature=temperature,
            system_prompt_id=system_prompt_id,
            description=description
        )
        
        if success:
            # Update home tab using modal-based view
            view = update_modal_based_home_tab(user_id)
            safe_publish_home_tab(user_id, view)
            
            # Send confirmation
            slack_client.chat_postMessage(
                channel=user_id,
                text=f"✅ Successfully updated persona '{persona_name}'! Changes are now active."
            )
            
            logger.info(f"Updated persona '{persona_name}' (ID: {persona_id}) for user {user_id}")
            return jsonify({"response_action": "clear"})
        else:
            return jsonify({
                "response_action": "errors",
                "errors": {"general": "Failed to update persona. Name might already exist."}
            })
        
    except Exception as e:
        logger.error(f"Error updating persona: {e}")
        return jsonify({
            "response_action": "errors",
            "errors": {"general": f"Unexpected error: {str(e)}"}
        })


def handle_ab_config_submission(payload: Dict[str, Any], user_id: str) -> Any:
    """Handle A/B configuration form submission."""
    try:
        values = payload.get("view", {}).get("state", {}).get("values", {})
        
        # Persona A configuration
        persona_a_id = values.get("ab_persona_a_selector", {}).get("ab_persona_a_selector", {}).get("selected_option", {}).get("value")
        persona_a_name = values.get("ab_persona_a_name", {}).get("ab_a_name_input", {}).get("value", "").strip()
        persona_a_model = values.get("ab_a_model_section", {}).get("ab_a_model_select", {}).get("selected_option", {}).get("value")
        persona_a_temp_str = values.get("ab_a_temperature_section", {}).get("ab_a_temperature_select", {}).get("selected_option", {}).get("value")
        
        # Persona B configuration
        persona_b_id = values.get("ab_persona_b_selector", {}).get("ab_persona_b_selector", {}).get("selected_option", {}).get("value")
        persona_b_name = values.get("ab_persona_b_name", {}).get("ab_b_name_input", {}).get("value", "").strip()
        persona_b_model = values.get("ab_b_model_section", {}).get("ab_b_model_select", {}).get("selected_option", {}).get("value")
        persona_b_temp_str = values.get("ab_b_temperature_section", {}).get("ab_b_temperature_select", {}).get("selected_option", {}).get("value")
        
        # Convert temperatures to float
        try:
            persona_a_temp = float(persona_a_temp_str) if persona_a_temp_str else 0.7
        except (ValueError, TypeError):
            persona_a_temp = 0.7
            
        try:
            persona_b_temp = float(persona_b_temp_str) if persona_b_temp_str else 0.7
        except (ValueError, TypeError):
            persona_b_temp = 0.7
        
        # Validate required fields
        if not all([persona_a_id, persona_b_id]):
            return jsonify({
                "response_action": "errors",
                "errors": {
                    "ab_persona_a_selector": "Persona A selection is required" if not persona_a_id else "",
                    "ab_persona_b_selector": "Persona B selection is required" if not persona_b_id else ""
                }
            })
        
        # Update A/B testing preferences
        UserPreferencesService.update_ab_persona(user_id, "response_a", int(persona_a_id))
        UserPreferencesService.update_ab_persona(user_id, "response_b", int(persona_b_id))
        
        # Update home tab using modal-based view
        view = update_modal_based_home_tab(user_id)
        safe_publish_home_tab(user_id, view)
        
        # Send confirmation message
        slack_client.chat_postMessage(
            channel=user_id,
            text="✅ A/B testing configuration saved! Your personas are ready for side-by-side comparison."
        )
        
        logger.info(f"Saved A/B testing configuration for user {user_id}")
        return jsonify({"response_action": "clear"})
        
    except Exception as e:
        logger.error(f"Error saving A/B testing configuration: {e}")
        slack_client.chat_postMessage(
            channel=payload.get("user", {}).get("id"),
            text=f"❌ Unexpected error: {str(e)}"
        )
        return jsonify({"status": "ok"})


def update_modal_based_home_tab(user_id: str) -> Dict[str, Any]:
    """Load modal-based home tab and populate with user's current settings."""
    try:
        view = load_json_view("app_home_modal_based")
        
        # Get user preferences and personas with error handling
        try:
            user_prefs = UserPreferencesService.get_user_preferences(user_id)
            personas = PersonaManager.get_user_personas(user_id)
        except Exception as db_error:
            logger.error(f"Database error loading user data for {user_id}: {db_error}")
            # Return view with error message
            for block in view['blocks']:
                if block.get('type') == 'section' and 'text' in block:
                    text = block['text'].get('text', '')
                    if 'persona_name' in text or 'Active Chat Persona' in text:
                        block['text']['text'] = "⚠️ *Database Connection Error*\nCannot load personas. Please try again later."
                        break
            return view
        
        # Update mode selector - default to chat mode
        current_mode = "chat_mode" if user_prefs.get('chat_mode_enabled', True) else "ab_testing"
        for block in view['blocks']:
            if block.get('type') == 'section' and block.get('accessory', {}).get('action_id') == 'mode_selector':
                for option in block['accessory']['options']:
                    if option['value'] == current_mode:
                        block['accessory']['initial_option'] = option
                        break
        
        # Update persona dropdowns with actual user personas
        persona_options = []
        if personas:  # Only build options if we have personas
            for persona in personas:
                name = persona['name']
                persona_options.append({
                    "text": {"type": "plain_text", "text": name},
                    "value": str(persona['id'])
                })
        
        # Get active persona for chat mode
        active_persona = None
        if user_prefs.get('active_persona_id') and personas:
            try:
                active_persona = PersonaManager.get_persona_by_id(user_prefs['active_persona_id'], user_id)
            except Exception as e:
                logger.error(f"Error loading active persona for {user_id}: {e}")
        
        if not active_persona and personas:
            # Find Assistant persona first, then fallback to first available
            assistant_persona = next((p for p in personas if p['name'].lower() == 'assistant'), None)
            if assistant_persona:
                active_persona = assistant_persona
                try:
                    PersonaManager.set_active_persona(user_id, assistant_persona['id'])
                except Exception as e:
                    logger.error(f"Error setting default active persona for {user_id}: {e}")
            else:
                active_persona = personas[0]
        
        # Get A/B testing personas with error handling
        persona_a = user_prefs.get('response_a', {}) if user_prefs else {}
        persona_b = user_prefs.get('response_b', {}) if user_prefs else {}
        
        # Update persona selectors and display current info
        for block in view['blocks']:
            accessory = block.get('accessory', {})
            action_id = accessory.get('action_id')
            
            # Update persona selector dropdowns - only if we have valid options
            if action_id == 'chat_persona_selector':
                if persona_options:  # Only update if we successfully loaded personas
                    accessory['options'] = persona_options
                    if active_persona:
                        persona_id = str(active_persona['id'])
                        for option in persona_options:
                            if option['value'] == persona_id:
                                accessory['initial_option'] = option
                                break
                else:
                    # Add database error message to placeholder
                    accessory['placeholder'] = {
                        "type": "plain_text", 
                        "text": "⚠️ Database error - cannot load personas"
                    }
            
            # Also update A/B testing persona dropdowns with available personas
            elif action_id in ['ab_persona_a_selector', 'ab_persona_b_selector']:
                if persona_options:  # Only update if we successfully loaded personas
                    accessory['options'] = persona_options
                    # Set initial selection if A/B persona is configured
                    if action_id == 'ab_persona_a_selector' and persona_a.get('persona_id'):
                        persona_id = str(persona_a['persona_id'])
                        for option in persona_options:
                            if option['value'] == persona_id:
                                accessory['initial_option'] = option
                                break
                    elif action_id == 'ab_persona_b_selector' and persona_b.get('persona_id'):
                        persona_id = str(persona_b['persona_id'])
                        for option in persona_options:
                            if option['value'] == persona_id:
                                accessory['initial_option'] = option
                                break
                else:
                    # Add database error message to placeholder
                    accessory['placeholder'] = {
                        "type": "plain_text", 
                        "text": "⚠️ Database error"
                    }
            
            # Update display text with current persona info
            if block.get('type') == 'section' and 'text' in block:
                text = block['text'].get('text', '')
                if active_persona:
                    # Replace individual field placeholders
                    if '{persona_name}' in text:
                        text = text.replace('{persona_name}', active_persona['name'])
                        block['text']['text'] = text
                    elif '{persona_description}' in text:
                        description = active_persona.get('description', 'No description provided')
                        text = text.replace('{persona_description}', description)
                        block['text']['text'] = text
                    elif '{persona_model}' in text:
                        model_display = {
                            'sonnet': 'Claude 4 Sonnet',
                            'opus': 'Claude 4 Opus'
                        }.get(active_persona['model'], active_persona['model'])
                        text = text.replace('{persona_model}', model_display)
                        block['text']['text'] = text
                    elif '{persona_temperature}' in text:
                        temp_value = str(active_persona['temperature'])
                        text = text.replace('{persona_temperature}', temp_value)
                        block['text']['text'] = text
                    elif '{persona_system_prompt}' in text:
                        # Show the system prompt with truncation to stay under Slack's 3000 char limit
                        full_prompt = active_persona.get('system_prompt', 'No system prompt defined')
                        # Reserve space for markdown formatting and other text (~200 chars)
                        max_prompt_length = 2800
                        if len(full_prompt) > max_prompt_length:
                            truncated_prompt = full_prompt[:max_prompt_length] + "..."
                            text = text.replace('{persona_system_prompt}', truncated_prompt)
                        else:
                            text = text.replace('{persona_system_prompt}', full_prompt)
                        block['text']['text'] = text
                
                # Handle A/B testing placeholders
                if '{persona_a_name}' in text or '{persona_b_name}' in text:
                    persona_a_name = "Not configured"
                    persona_b_name = "Not configured"
                    if persona_a.get('persona_id') and personas:
                        try:
                            persona_a_data = PersonaManager.get_persona_by_id(persona_a['persona_id'], user_id)
                            if persona_a_data:
                                persona_a_name = persona_a_data['name']
                        except Exception as e:
                            logger.error(f"Error loading persona A data for {user_id}: {e}")
                    if persona_b.get('persona_id') and personas:
                        try:
                            persona_b_data = PersonaManager.get_persona_by_id(persona_b['persona_id'], user_id)
                            if persona_b_data:
                                persona_b_name = persona_b_data['name']
                        except Exception as e:
                            logger.error(f"Error loading persona B data for {user_id}: {e}")
                    
                    text = text.replace('{persona_a_name}', persona_a_name)
                    text = text.replace('{persona_b_name}', persona_b_name)
                    block['text']['text'] = text
        
        return view
        
    except Exception as e:
        logger.error(f"Error building modal-based home tab for user {user_id}: {e}")
        # Fallback to basic view
        return load_json_view("app_home_modal_based")


def handle_edit_chat_persona_modal(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle opening the edit persona modal with pre-populated data."""
    try:
        user_id = payload.get("user", {}).get("id")
        trigger_id = payload.get("trigger_id")
        
        if not user_id or not trigger_id:
            return jsonify({"error": "Missing data"}), 400
        
        # Get the current active persona
        active_persona = PersonaManager.get_active_persona(user_id)
        
        if not active_persona:
            slack_client.chat_postMessage(
                channel=user_id,
                text="❌ No active persona found. Please select a persona first."
            )
            return jsonify({"status": "ok"})
        
        # Load the modal template
        modal = load_json_view("edit_persona_modal")
        
        # Pre-populate the modal with current persona data
        for block in modal.get("blocks", []):
            block_id = block.get("block_id")
            element = block.get("element", {})
            
            if block_id == "persona_name" and element.get("action_id") == "name_input":
                element["initial_value"] = active_persona["name"]
            elif block_id == "persona_description" and element.get("action_id") == "description_input":
                element["initial_value"] = active_persona.get("description", "")
            elif block_id == "system_prompt" and element.get("action_id") == "prompt_input":
                element["initial_value"] = active_persona.get("system_prompt", "")
            
            # Handle accessory elements (radio buttons, selects)
            accessory = block.get("accessory", {})
            if block_id == "model_selection" and accessory.get("action_id") == "model_select":
                # Set initial model selection
                for option in accessory.get("options", []):
                    if option["value"] == active_persona["model"]:
                        accessory["initial_option"] = option
                        break
            elif block_id == "temperature_section" and accessory.get("action_id") == "temperature_select":
                # Set initial temperature selection
                temp_value = str(active_persona["temperature"])
                for option in accessory.get("options", []):
                    if option["value"] == temp_value:
                        accessory["initial_option"] = option
                        break
        
        # Add persona info to modal title and metadata
        modal["private_metadata"] = json.dumps({
            "persona_id": active_persona["id"],
            "action": "edit_persona"
        })
        
        # Update modal text with persona name
        for block in modal.get("blocks", []):
            if block.get("type") == "section" and "text" in block:
                text = block["text"].get("text", "")
                if "{persona_name}" in text:
                    block["text"]["text"] = text.replace("{persona_name}", active_persona["name"])
        
        # Open the modal
        slack_client.views_open(
            trigger_id=trigger_id,
            view=modal
        )
        
        logger.info(f"Opened edit persona modal for user {user_id}, persona: {active_persona['name']}")
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error opening edit persona modal: {e}")
        slack_client.chat_postMessage(
            channel=user_id,
            text="❌ Failed to open edit modal. Please try again."
        )
        return jsonify({"error": "Failed to open modal"}), 500


def handle_configure_ab_testing_modal(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle opening the A/B testing configuration modal."""
    try:
        user_id = payload.get("user", {}).get("id")
        trigger_id = payload.get("trigger_id")
        
        if not user_id or not trigger_id:
            return jsonify({"error": "Missing data"}), 400
        
        # Get current A/B preferences
        preferences = UserPreferencesService.get_user_preferences(user_id)
        persona_a = preferences.get("persona_a", {})
        persona_b = preferences.get("persona_b", {})
        
        # Get persona data for pre-population
        persona_a_data = None
        persona_b_data = None
        
        if persona_a.get("persona_id"):
            persona_a_data = PersonaManager.get_persona_by_id(persona_a["persona_id"], user_id)
        if persona_b.get("persona_id"):
            persona_b_data = PersonaManager.get_persona_by_id(persona_b["persona_id"], user_id)
        
        # Load the modal template
        modal = load_json_view("ab_config_modal")
        
        # Get all available personas for the selectors
        all_personas = PersonaManager.get_user_personas(user_id)
        persona_options = []
        for persona in all_personas:
            name = persona['name']
            
            persona_options.append({
                "text": {"type": "plain_text", "text": name},
                "value": str(persona['id'])
            })
        
        # Pre-populate the modal
        for block in modal.get("blocks", []):
            accessory = block.get("accessory", {})
            element = block.get("element", {})
            block_id = block.get("block_id")
            
            # Update persona selector options
            if accessory.get("action_id") in ["ab_persona_a_selector", "ab_persona_b_selector"]:
                accessory["options"] = persona_options
                
                # Set initial selection
                if accessory.get("action_id") == "ab_persona_a_selector" and persona_a_data:
                    for option in persona_options:
                        if option["value"] == str(persona_a_data["id"]):
                            accessory["initial_option"] = option
                            break
                elif accessory.get("action_id") == "ab_persona_b_selector" and persona_b_data:
                    for option in persona_options:
                        if option["value"] == str(persona_b_data["id"]):
                            accessory["initial_option"] = option
                            break
            
            # Pre-populate form fields
            if persona_a_data:
                if block_id == "ab_persona_a_name" and element.get("action_id") == "ab_a_name_input":
                    element["initial_value"] = persona_a_data["name"]
                elif accessory.get("action_id") == "ab_a_model_select":
                    for option in accessory.get("options", []):
                        if option["value"] == persona_a_data["model"]:
                            accessory["initial_option"] = option
                            break
                elif accessory.get("action_id") == "ab_a_temperature_select":
                    temp_value = str(persona_a_data["temperature"])
                    for option in accessory.get("options", []):
                        if option["value"] == temp_value:
                            accessory["initial_option"] = option
                            break
            
            if persona_b_data:
                if block_id == "ab_persona_b_name" and element.get("action_id") == "ab_b_name_input":
                    element["initial_value"] = persona_b_data["name"]
                elif accessory.get("action_id") == "ab_b_model_select":
                    for option in accessory.get("options", []):
                        if option["value"] == persona_b_data["model"]:
                            accessory["initial_option"] = option
                            break
                elif accessory.get("action_id") == "ab_b_temperature_select":
                    temp_value = str(persona_b_data["temperature"])
                    for option in accessory.get("options", []):
                        if option["value"] == temp_value:
                            accessory["initial_option"] = option
                            break
        
        # Open the modal
        slack_client.views_open(
            trigger_id=trigger_id,
            view=modal
        )
        
        logger.info(f"Opened A/B testing configuration modal for user {user_id}")
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error opening A/B testing modal: {e}")
        slack_client.chat_postMessage(
            channel=user_id,
            text="❌ Failed to open A/B testing configuration modal. Please try again."
        )
        return jsonify({"error": "Failed to open modal"}), 500


def handle_delete_persona(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle persona deletion with confirmation."""
    try:
        user_id = payload.get("user", {}).get("id")
        
        if not user_id:
            return jsonify({"error": "Missing user ID"}), 400
        
        # Get the current active persona
        active_persona = PersonaManager.get_active_persona(user_id)
        
        if not active_persona:
            slack_client.chat_postMessage(
                channel=user_id,
                text="❌ No active persona found to delete."
            )
            return jsonify({"status": "ok"})
        
        # Send confirmation message with buttons
        confirmation_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Are you sure you want to delete the persona '{active_persona['name']}'?*\n\nThis action cannot be undone."
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🗑️ Yes, Delete"},
                        "action_id": "confirm_delete_persona",
                        "style": "danger",
                        "value": str(active_persona["id"])
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Cancel"},
                        "action_id": "cancel_delete_persona"
                    }
                ]
            }
        ]
        
        slack_client.chat_postMessage(
            channel=user_id,
            blocks=confirmation_blocks,
            text=f"Confirm deletion of persona '{active_persona['name']}'?"
        )
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling persona deletion: {e}")
        slack_client.chat_postMessage(
            channel=user_id,
            text="❌ Failed to process delete request. Please try again."
        )
        return jsonify({"error": "Failed to process delete request"}), 500


def handle_ab_vote(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle A/B test voting."""
    try:
        # Parse the vote data
        vote_data = json.loads(action.get("value", "{}"))
        test_id = vote_data.get("test_id")
        variant = vote_data.get("variant")
        voter_user_id = payload.get("user", {}).get("id")
        
        if not all([test_id, variant, voter_user_id]):
            logger.error("Missing required vote data")
            return jsonify({"error": "Invalid vote data"}), 400
        
        # Check if user already voted
        existing_vote = ABVote.query.filter_by(
            test_id=test_id, 
            user_id=voter_user_id
        ).first()
        
        if existing_vote:
            # Update existing vote
            existing_vote.chosen_variant = variant
            logger.info(f"Updated vote for user {voter_user_id} in test {test_id} to variant {variant}")
        else:
            # Create new vote
            new_vote = ABVote(
                test_id=test_id,
                user_id=voter_user_id,
                chosen_variant=variant
            )
            db.session.add(new_vote)
            logger.info(f"Created new vote for user {voter_user_id} in test {test_id} for variant {variant}")
        
        db.session.commit()
        
        # Send confirmation message
        channel_id = payload.get("channel", {}).get("id")
        user_id = payload.get("user", {}).get("id")
        persona_name = vote_data.get("persona_name", variant)
        
        confirmation_text = f"<@{user_id}> Thanks for your feedback! You voted for Response {variant} ({persona_name})."
        
        slack_client.chat_postMessage(
            channel=channel_id,
            text=confirmation_text,
            thread_ts=payload.get("message", {}).get("thread_ts")
        )
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling A/B vote: {e}")
        return jsonify({"error": "Failed to process vote"}), 500


# ==========================================
# ERROR TRACKING AND MONITORING
# ==========================================

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify app and database status."""
    try:
        # Test database connection using newer SQLAlchemy API
        from sqlalchemy import text
        with app.app_context():
            db.session.execute(text('SELECT 1'))
            db.session.commit()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 503

# Additional monitoring endpoints
@app.route("/status", methods=["GET"])
def status_check():
    """Detailed status check with more information."""
    try:
        import time
        start_time = time.time()
        
        # Test database
        db_status = "unknown"
        db_latency = None
        try:
            from sqlalchemy import text
            db_start = time.time()
            with app.app_context():
                result = db.session.execute(text('SELECT COUNT(*) FROM user_preferences'))
                row_count = result.scalar()
                db.session.commit()
            db_latency = round((time.time() - db_start) * 1000, 2)  # ms
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)[:100]}"
        
        # # TODO Test Anthropic API
        # anthropic_status = "unknown"
        # try:
        #     from services.anthropic import claude, MODELS
        #     # Quick test with minimal tokens using the configured model
        #     model_name = MODELS.get("sonnet", "claude-3-5-sonnet-20241022")
        #     test_response = claude.messages.create(
        #         model=model_name,
        #         max_tokens=1,
        #         messages=[{"role": "user", "content": "hi"}]
        #     )
        #     anthropic_status = "connected"
        # except Exception as e:
        #     anthropic_status = f"error: {str(e)[:100]}"
        
        total_time = round((time.time() - start_time) * 1000, 2)
        
        return jsonify({
            "status": "ok",
            "timestamp": time.time(),
            "checks": {
                "database": {
                    "status": db_status,
                    "latency_ms": db_latency,
                    "user_count": row_count if db_status == "connected" else None
                },
                "anthropic": {
                    "status": anthropic_status
                }
            },
            "response_time_ms": total_time
        })
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return jsonify({
            "status": "error", 
            "error": str(e),
            "timestamp": time.time()
        }), 500

# Request logging middleware
@app.before_request
def log_request_info():
    """Log request information for debugging."""
    # Skip logging for health checks to avoid noise
    if request.path in ['/health', '/status']:
        return
        
    logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")
    
    # Log payload size for POST requests
    if request.method == 'POST' and request.content_length:
        logger.info(f"Request size: {request.content_length} bytes")

@app.after_request
def log_response_info(response):
    """Log response information."""
    # Skip logging for health checks
    if request.path in ['/health', '/status']:
        return response
        
    logger.info(f"Response: {response.status_code} for {request.method} {request.path}")
    
    # Log errors with more detail
    if response.status_code >= 400:
        logger.warning(f"Error response {response.status_code}: {request.method} {request.path}")
    
    return response

# Simple error tracking (in memory - for basic monitoring)
error_tracker = {
    'recent_errors': [],
    'error_counts': {}
}

def track_error(error_type, error_message, error_id=None):
    """Track errors for monitoring."""
    import time
    
    error_entry = {
        'timestamp': time.time(),
        'type': error_type,
        'message': error_message[:200],  # Truncate long messages
        'error_id': error_id
    }
    
    # Keep only last 50 errors
    error_tracker['recent_errors'].append(error_entry)
    if len(error_tracker['recent_errors']) > 50:
        error_tracker['recent_errors'].pop(0)
    
    # Count by type
    error_tracker['error_counts'][error_type] = error_tracker['error_counts'].get(error_type, 0) + 1


@app.route("/errors", methods=["GET"])
def error_summary():
    """Get recent errors summary for monitoring."""
    import time
    
    # Only show errors from last 24 hours
    cutoff_time = time.time() - (24 * 60 * 60)
    recent_errors = [
        error for error in error_tracker['recent_errors'] 
        if error['timestamp'] > cutoff_time
    ]
    
    return jsonify({
        "status": "ok",
        "error_summary": {
            "total_recent_errors": len(recent_errors),
            "error_counts": error_tracker['error_counts'],
            "recent_errors": recent_errors[-10:],  # Last 10 errors
        },
        "timestamp": time.time()
    })

# ==========================================
# ERROR HANDLERS (Following Flask best practices)
# ==========================================

from werkzeug.exceptions import HTTPException
import traceback

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 Internal Server Error."""
    error_id = f"ERR-{int(os.urandom(4).hex(), 16)}"  # Generate short error ID
    logger.error(f"Internal Server Error [{error_id}]: {e}")
    logger.error(f"Traceback [{error_id}]: {traceback.format_exc()}")
    
    # Track error for monitoring
    track_error("500_internal_error", str(e), error_id)
    
    # Return JSON for API endpoints, HTML for others
    if request.path.startswith('/event') or request.path.startswith('/interactive'):
        return jsonify({
            "error": "Internal server error",
            "error_id": error_id,
            "status": "error"
        }), 500
    
    return jsonify({
        "error": "Internal server error", 
        "error_id": error_id,
        "message": "Something went wrong. Please try again later."
    }), 500

@app.errorhandler(404)
def not_found_error(e):
    """Handle 404 Not Found Error."""
    logger.warning(f"404 error: {request.url}")
    track_error("404_not_found", f"Path: {request.path}")
    
    return jsonify({
        "error": "Not found",
        "message": "The requested resource was not found.",
        "path": request.path
    }), 404

@app.errorhandler(400)
def bad_request_error(e):
    """Handle 400 Bad Request Error."""
    logger.warning(f"Bad request: {request.url} - {e}")
    track_error("400_bad_request", str(e))
    
    return jsonify({
        "error": "Bad request",
        "message": "Invalid request data or parameters."
    }), 400

@app.errorhandler(405)
def method_not_allowed_error(e):
    """Handle 405 Method Not Allowed Error."""
    logger.warning(f"Method not allowed: {request.method} {request.url}")
    track_error("405_method_not_allowed", f"{request.method} {request.path}")
    
    return jsonify({
        "error": "Method not allowed",
        "message": f"Method {request.method} is not allowed for this endpoint."
    }), 405

# Database-specific error handler
from sqlalchemy.exc import OperationalError, DatabaseError
from pymysql.err import OperationalError as PyMySQLOperationalError

@app.errorhandler(OperationalError)
@app.errorhandler(PyMySQLOperationalError)
@app.errorhandler(DatabaseError)
def database_error(e):
    """Handle database connection and operational errors."""
    error_id = f"DB-ERR-{int(os.urandom(4).hex(), 16)}"
    logger.error(f"DATABASE CONNECTION FAILURE [{error_id}]: {e}")
    
    # Track database error
    track_error("database_connection_failure", str(e), error_id)
    
    # For Slack API endpoints, return 200 but with clear error messaging
    if request.path.startswith('/event') or request.path.startswith('/interactive'):
        # Try to send user-friendly message to Slack if possible
        try:
            payload = request.get_json() or {}
            if request.path.startswith('/interactive'):
                payload = json.loads(request.form.get("payload", "{}"))
            
            user_id = payload.get("user", {}).get("id") or payload.get("event", {}).get("user")
            if user_id:
                slack_client.chat_postMessage(
                    channel=user_id,
                    text=f"🚨 **DATABASE CONNECTION FAILURE** [{error_id}]\n\nThe database is currently unreachable. This is causing the persona system to malfunction.\n\n**Error:** {str(e)[:200]}\n\nPlease contact the administrator."
                )
        except Exception as slack_error:
            logger.error(f"Failed to send database error message to Slack: {slack_error}")
        
        return jsonify({"status": "ok", "message": f"Database connection failure: {error_id}"}), 200
    
    return jsonify({
        "error": "Database connection failure",
        "error_id": error_id,
        "message": f"Database is unreachable. Error ID: {error_id}",
        "details": str(e)[:200]
    }), 503

# Generic exception handler for unhandled exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    """Handle unexpected exceptions."""
    # Pass through HTTP errors to their specific handlers
    if isinstance(e, HTTPException):
        return e
    
    # Handle non-HTTP exceptions
    error_id = f"UNHANDLED-{int(os.urandom(4).hex(), 16)}"
    logger.error(f"Unhandled Exception [{error_id}]: {type(e).__name__}: {e}")
    logger.error(f"Traceback [{error_id}]: {traceback.format_exc()}")
    
    # Track unhandled exception
    track_error("unhandled_exception", f"{type(e).__name__}: {str(e)}", error_id)
    
    # For Slack endpoints, try to be graceful
    if request.path.startswith('/event') or request.path.startswith('/interactive'):
        try:
            payload = request.get_json() or {}
            if request.path.startswith('/interactive'):
                payload = json.loads(request.form.get("payload", "{}"))
            
            user_id = payload.get("user", {}).get("id") or payload.get("event", {}).get("user")
            if user_id:
                slack_client.chat_postMessage(
                    channel=user_id,
                    text="⚠️ I encountered an unexpected error. Please try again."
                )
        except Exception as slack_error:
            logger.error(f"Failed to send exception error message to Slack: {slack_error}")
        
        return jsonify({"status": "ok", "message": "Unexpected error occurred"}), 200
    
    return jsonify({
        "error": "Unexpected error",
        "error_id": error_id,
        "message": "An unexpected error occurred. Please try again later."
    }), 500

# Admin Dashboard Routes
from flask import render_template, flash, redirect, url_for
from datetime import datetime

@app.route("/admin")
def admin_dashboard():
    """
    Main admin dashboard with overview statistics.
    """
    try:
        # Get statistics
        total_users = UserPreferences.query.count()
        total_prompts = SystemPrompt.query.count()
        total_personas = AIPersona.query.count()
        total_tests = ABTest.query.count()
        
        stats = {
            'total_users': total_users,
            'total_prompts': total_prompts,
            'total_personas': total_personas,
            'total_tests': total_tests
        }
        
        # Get recent activity (simplified for now)
        recent_activity = [
            {
                'icon': 'user-plus',
                'description': f'{total_users} total users registered',
                'timestamp': 'System stats'
            },
            {
                'icon': 'file-text',
                'description': f'{total_prompts} system prompts available',
                'timestamp': 'System stats'
            },
            {
                'icon': 'user-circle',
                'description': f'{total_personas} AI personas created',
                'timestamp': 'System stats'
            }
        ]
        
        return render_template('admin_dashboard.html', stats=stats, recent_activity=recent_activity)
        
    except Exception as e:
        logger.error(f"Error loading admin dashboard: {e}")
        flash('Error loading dashboard', 'error')
        return render_template('admin_dashboard.html', stats={'total_users': 0, 'total_prompts': 0, 'total_personas': 0, 'total_tests': 0}, recent_activity=[])

@app.route("/admin/users")
def admin_users():
    """
    User preferences management page.
    """
    try:
        # Get all user preferences with related persona names
        users = db.session.query(UserPreferences).all()
        
        # Prepare user data with persona names
        user_data = []
        for user in users:
            active_persona_name = None
            ab_persona_a_name = None
            ab_persona_b_name = None
            
            if user.active_persona_id:
                active_persona = AIPersona.query.get(user.active_persona_id)
                active_persona_name = active_persona.name if active_persona else None
                
            if user.ab_testing_persona_a_id:
                persona_a = AIPersona.query.get(user.ab_testing_persona_a_id)
                ab_persona_a_name = persona_a.name if persona_a else None
                
            if user.ab_testing_persona_b_id:
                persona_b = AIPersona.query.get(user.ab_testing_persona_b_id)
                ab_persona_b_name = persona_b.name if persona_b else None
            
            user_data.append({
                'user_id': user.user_id,
                'chat_mode_enabled': user.chat_mode_enabled,
                'active_persona': active_persona_name,
                'ab_persona_a': ab_persona_a_name,
                'ab_persona_b': ab_persona_b_name,
                'created_at': user.created_at,
                'updated_at': user.updated_at,
                'active_persona_id': user.active_persona_id,
                'ab_testing_persona_a_id': user.ab_testing_persona_a_id,
                'ab_testing_persona_b_id': user.ab_testing_persona_b_id
            })
        
        # Get all available personas for the edit form
        available_personas = AIPersona.query.all()
        
        return render_template('admin_users.html', users=user_data, available_personas=available_personas)
        
    except Exception as e:
        logger.error(f"Error loading users page: {e}")
        flash('Error loading users', 'error')
        return render_template('admin_users.html', users=[], available_personas=[])

@app.route("/admin/users/<user_id>", methods=['GET'])
def admin_user_get(user_id):
    """
    Get specific user data for editing.
    """
    try:
        user = UserPreferences.query.filter_by(user_id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user_id': user.user_id,
            'chat_mode_enabled': user.chat_mode_enabled,
            'active_persona_id': user.active_persona_id,
            'ab_testing_persona_a_id': user.ab_testing_persona_a_id,
            'ab_testing_persona_b_id': user.ab_testing_persona_b_id
        })
        
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/users/<user_id>", methods=['POST'])
def admin_user_update(user_id):
    """
    Update user preferences.
    """
    try:
        user = UserPreferences.query.filter_by(user_id=user_id).first()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('admin_users'))
        
        # Update fields
        user.chat_mode_enabled = 'chat_mode_enabled' in request.form
        user.active_persona_id = request.form.get('active_persona_id') or None
        user.ab_testing_persona_a_id = request.form.get('ab_testing_persona_a_id') or None
        user.ab_testing_persona_b_id = request.form.get('ab_testing_persona_b_id') or None
        user.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Updated preferences for user {user_id}', 'success')
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/users/<user_id>", methods=['DELETE'])
def admin_user_delete(user_id):
    """
    Delete user preferences.
    """
    try:
        user = UserPreferences.query.filter_by(user_id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/prompts")
def admin_prompts():
    """
    System prompts management page.
    """
    try:
        prompts = SystemPrompt.query.order_by(SystemPrompt.is_default.desc(), SystemPrompt.usage_count.desc()).all()
        return render_template('admin_prompts.html', prompts=prompts)
        
    except Exception as e:
        logger.error(f"Error loading prompts page: {e}")
        flash('Error loading prompts', 'error')
        return render_template('admin_prompts.html', prompts=[])

@app.route("/admin/prompts/create", methods=['GET', 'POST'])
def admin_prompts_create():
    """
    Create new system prompt.
    """
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            user_id = request.form.get('user_id')
            content = request.form.get('content')
            is_default = 'is_default' in request.form
            
            if not all([title, user_id, content]):
                flash('Title, User ID, and Content are required', 'error')
                return render_template('admin_prompts_create.html')
            
            # Use SystemPromptManager to create the prompt
            prompt = SystemPromptManager.create_prompt(
                user_id=user_id,
                title=title,
                content=content,
                description=description
            )
            
            if not prompt:
                flash('Failed to create prompt. Title might already exist for this user.', 'error')
                return render_template('admin_prompts_create.html')
            
            # Update is_default if needed
            if is_default:
                system_prompt = SystemPrompt.query.get(prompt['id'])
                system_prompt.is_default = True
                db.session.commit()
            
            flash(f'Successfully created prompt "{title}"', 'success')
            return redirect(url_for('admin_prompts'))
            
        except Exception as e:
            logger.error(f"Error creating prompt: {e}")
            flash('Error creating prompt', 'error')
            return render_template('admin_prompts_create.html')
    
    return render_template('admin_prompts_create.html')

@app.route("/admin/prompts/<int:prompt_id>", methods=['GET'])
def admin_prompt_get(prompt_id):
    """
    Get specific prompt data.
    """
    try:
        prompt = SystemPrompt.query.get_or_404(prompt_id)
        return jsonify({
            'id': prompt.id,
            'title': prompt.title,
            'description': prompt.description,
            'content': prompt.content,
            'user_id': prompt.user_id,
            'is_default': prompt.is_default,
            'usage_count': prompt.usage_count
        })
        
    except Exception as e:
        logger.error(f"Error getting prompt {prompt_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/prompts/<int:prompt_id>", methods=['POST'])
def admin_prompt_update(prompt_id):
    """
    Update system prompt.
    """
    try:
        prompt = SystemPrompt.query.get_or_404(prompt_id)
        
        prompt.title = request.form.get('title', prompt.title)
        prompt.description = request.form.get('description', prompt.description)
        prompt.content = request.form.get('content', prompt.content)
        prompt.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating prompt {prompt_id}: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/prompts/<int:prompt_id>", methods=['DELETE'])
def admin_prompt_delete(prompt_id):
    """
    Delete system prompt.
    """
    try:
        prompt = SystemPrompt.query.get_or_404(prompt_id)
        
        # Check if prompt is in use by any personas
        personas_using = AIPersona.query.filter_by(system_prompt_id=prompt_id).count()
        if personas_using > 0:
            return jsonify({'error': f'Cannot delete prompt. It is being used by {personas_using} personas.'}), 400
        
        db.session.delete(prompt)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting prompt {prompt_id}: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/personas")
def admin_personas():
    """
    AI personas management page.
    """
    try:
        # Query directly since PersonaManager.get_user_personas expects specific user
        personas_query = AIPersona.query.order_by(AIPersona.is_favorite.desc(), AIPersona.usage_count.desc()).all()
        personas = [PersonaManager._persona_to_dict(p) for p in personas_query]
        
        # Get available prompts for editing
        available_prompts = SystemPrompt.query.all()
        
        return render_template('admin_personas.html', personas=personas, available_prompts=available_prompts)
        
    except Exception as e:
        logger.error(f"Error loading personas page: {e}")
        flash('Error loading personas', 'error')
        return render_template('admin_personas.html', personas=[], available_prompts=[])

@app.route("/admin/personas/create", methods=['GET', 'POST'])
def admin_personas_create():
    """
    Create new AI persona.
    """
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            user_id = request.form.get('user_id')
            model = request.form.get('model')
            temperature = float(request.form.get('temperature', 0.7))
            system_prompt_id = int(request.form.get('system_prompt_id'))
            
            if not all([name, user_id, model, system_prompt_id]):
                flash('Name, User ID, Model, and System Prompt are required', 'error')
                return render_template('admin_personas_create.html', available_prompts=SystemPrompt.query.all())
            
            # Use PersonaManager to create the persona
            persona = PersonaManager.create_persona(
                user_id=user_id,
                name=name,
                model=model,
                temperature=temperature,
                system_prompt_id=system_prompt_id,
                description=description
            )
            
            if not persona:
                flash('Failed to create persona. Name might already exist for this user.', 'error')
                return render_template('admin_personas_create.html', available_prompts=SystemPrompt.query.all())
            
            flash(f'Successfully created persona "{name}"', 'success')
            return redirect(url_for('admin_personas'))
            
        except Exception as e:
            logger.error(f"Error creating persona: {e}")
            flash('Error creating persona', 'error')
            return render_template('admin_personas_create.html', available_prompts=SystemPrompt.query.all())
    
    available_prompts = SystemPrompt.query.all()
    return render_template('admin_personas_create.html', available_prompts=available_prompts)

@app.route("/admin/personas/<int:persona_id>", methods=['GET'])
def admin_persona_get(persona_id):
    """
    Get specific persona data.
    """
    try:
        persona = AIPersona.query.get_or_404(persona_id)
        persona_dict = PersonaManager._persona_to_dict(persona)
        return jsonify(persona_dict)
        
    except Exception as e:
        logger.error(f"Error getting persona {persona_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/personas/<int:persona_id>", methods=['POST'])
def admin_persona_update(persona_id):
    """
    Update AI persona.
    """
    try:
        name = request.form.get('name')
        description = request.form.get('description')
        model = request.form.get('model')
        temperature = float(request.form.get('temperature', 0.7)) if request.form.get('temperature') else None
        system_prompt_id = int(request.form.get('system_prompt_id')) if request.form.get('system_prompt_id') else None
        
        # Use PersonaManager to update
        success = PersonaManager.update_persona(
            persona_id=persona_id,
            user_id="ADMIN_UPDATE",  # We'll bypass user validation in admin
            name=name,
            model=model,
            temperature=temperature,
            system_prompt_id=system_prompt_id,
            description=description
        )
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update persona'}), 400
            
    except Exception as e:
        logger.error(f"Error updating persona {persona_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route("/admin/personas/<int:persona_id>", methods=['DELETE'])
def admin_persona_delete(persona_id):
    """
    Delete AI persona.
    """
    try:
        persona = AIPersona.query.get_or_404(persona_id)
        
        # Check if persona is in use by user preferences
        active_users = UserPreferences.query.filter_by(active_persona_id=persona_id).count()
        ab_a_users = UserPreferences.query.filter_by(ab_testing_persona_a_id=persona_id).count()
        ab_b_users = UserPreferences.query.filter_by(ab_testing_persona_b_id=persona_id).count()
        
        total_usage = active_users + ab_a_users + ab_b_users
        if total_usage > 0:
            return jsonify({'error': f'Cannot delete persona. It is being used by {total_usage} user configurations.'}), 400
        
        db.session.delete(persona)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting persona {persona_id}: {e}")
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500

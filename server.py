import json
import os
import ssl
from typing import Any, Dict
import logging

import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from flask import Flask, jsonify, request
from flask_migrate import Migrate

from config import config
from models import db, ABVote
from services import (
    get_conversation_history,
    get_standard_claude_response,
    ABTestingService,
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
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            # Don't fail startup - let the app run and retry later

# Flask CLI Commands
@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    print("Database tables created.")

@app.cli.command()
def populate_defaults():
    """Populate database with default system prompts and personas."""
    from services import SystemPromptManager, PersonaManager
    
    # Create default system prompts
    default_prompts = [
        {
            'title': 'Assistant',
            'description': 'General helpful assistant',
            'content': 'You are a helpful AI assistant. Provide clear, accurate, and balanced responses. Be concise but thorough.'
        },
        {
            'title': 'Creative Writer',
            'description': 'Expressive and imaginative responses',
            'content': 'You are a creative and expressive AI assistant. Think outside the box, use vivid language, and bring imagination to your responses. Be artistic and inspiring.'
        },
        {
            'title': 'Technical Analyst',
            'description': 'Logical and precise analysis',
            'content': 'You are an analytical AI assistant focused on logic, precision, and data-driven insights. Provide structured, methodical responses with clear reasoning.'
        },
        {
            'title': 'Code Helper',
            'description': 'Programming assistance',
            'content': 'You are an expert software engineer. Provide clear, efficient code solutions with explanations. Always include error handling and best practices.'
        },
        {
            'title': 'Writing Coach',
            'description': 'Style and clarity guidance',
            'content': 'You are a professional writing coach. Help improve clarity, style, and structure. Provide specific suggestions with examples.'
        }
    ]
    
    # Use a system user ID for default prompts
    system_user_id = "SYSTEM_DEFAULT"
    
    for prompt_data in default_prompts:
        try:
            prompt = SystemPromptManager.create_prompt(
                user_id=system_user_id,
                title=prompt_data['title'],
                content=prompt_data['content'],
                description=prompt_data['description']
            )
            if prompt:
                # Mark as default
                from models import SystemPrompt
                system_prompt = SystemPrompt.query.get(prompt['id'])
                system_prompt.is_default = True
                db.session.commit()
                print(f"Created default prompt: {prompt_data['title']}")
            else:
                print(f"Prompt {prompt_data['title']} already exists")
        except Exception as e:
            print(f"Error creating prompt {prompt_data['title']}: {e}")
    
    print("Default system prompts populated.")

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


def truncate_slack_text_recursive(obj: Any, max_length: int = 70) -> Any:
    """
    Recursively truncate all text elements in a Slack view to ensure they don't exceed max_length.
    This prevents Slack API errors due to text being too long.
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "text" and isinstance(value, str):
                # Truncate text directly
                if len(value) > max_length:
                    result[key] = value[:max_length-3] + "..."
                else:
                    result[key] = value
            else:
                # Recursively process nested objects
                result[key] = truncate_slack_text_recursive(value, max_length)
        return result
    elif isinstance(obj, list):
        # Process each item in the list
        return [truncate_slack_text_recursive(item, max_length) for item in obj]
    else:
        # Return primitive values unchanged
        return obj


def update_home_tab_with_user_data(user_id: str) -> Dict[str, Any]:
    """Load unified home tab and populate with user's current settings."""
    try:
        view = load_json_view("app_home_unified")
        
        # Get user preferences and personas
        user_prefs = UserPreferencesService.get_user_preferences(user_id)
        personas = PersonaManager.get_user_personas(user_id)
        
        # Update mode selector
        current_mode = "chat_mode" if user_prefs.get('chat_mode_enabled') else "ab_testing"
        for block in view['blocks']:
            if block.get('type') == 'section' and block.get('accessory', {}).get('action_id') == 'mode_selector':
                for option in block['accessory']['options']:
                    if option['value'] == current_mode:
                        block['accessory']['initial_option'] = option
                        break
        
        # Update persona dropdowns with actual user personas
        persona_options = []
        for persona in personas:
            # Construct option text (global truncation will handle length limits)
            name = persona['name']
            description = persona.get('description', 'Custom persona')
            option_text = f"{name} - {description}"
            
            persona_options.append({
                "text": {
                    "type": "plain_text",
                    "text": option_text
                },
                "value": str(persona['id'])
            })
        
        # Update all persona selectors
        for block in view['blocks']:
            accessory = block.get('accessory', {})
            action_id = accessory.get('action_id')
            
            if action_id in ['ab_persona_a_selector', 'ab_persona_b_selector', 'chat_persona_selector']:
                if persona_options:
                    accessory['options'] = persona_options
                    
                    # Set initial selections based on user preferences
                    if action_id == 'ab_persona_a_selector' and user_prefs.get('response_a', {}).get('persona_id'):
                        persona_id = str(user_prefs['response_a']['persona_id'])
                        for option in persona_options:
                            if option['value'] == persona_id:
                                accessory['initial_option'] = option
                                break
                    elif action_id == 'ab_persona_b_selector' and user_prefs.get('response_b', {}).get('persona_id'):
                        persona_id = str(user_prefs['response_b']['persona_id'])
                        for option in persona_options:
                            if option['value'] == persona_id:
                                accessory['initial_option'] = option
                                break
                    elif action_id == 'chat_persona_selector' and user_prefs.get('active_persona_id'):
                        persona_id = str(user_prefs['active_persona_id'])
                        for option in persona_options:
                            if option['value'] == persona_id:
                                accessory['initial_option'] = option
                                break
        
        return view
        
    except Exception as e:
        logger.error(f"Error building home tab for user {user_id}: {e}")
        # Fallback to basic view
        return load_json_view("app_home_unified")

def safe_publish_home_tab(user_id: str, view: Dict[str, Any] = None) -> bool:
    """
    Safely publish home tab updates with error handling.
    Returns True if successful, False otherwise.
    """
    try:
        if view is None:
            view = update_home_tab_with_user_data(user_id)
        
        # Apply text truncation to the entire view to prevent Slack API errors
        truncated_view = truncate_slack_text_recursive(view)
        
        slack_client.views_publish(user_id=user_id, view=truncated_view)
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


def handle_message(message: Dict[str, Any], client: WebClient) -> None:
    """Handle incoming messages using ChatService for mode-aware responses."""
    # Initialize processed messages dict if it doesn't exist - TODO move this to a db
    if not hasattr(handle_message, 'processed_messages'):
        handle_message.processed_messages = {}

    bot_user_id = client.auth_test()["user_id"]
    user = message.get("user")
    
    # Ignore if the message is from the bot itself
    if user == bot_user_id:
        logger.info("Skipping bot's own message")
        return

    channel_type = message.get("channel_type") 
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    message_ts = message.get("ts")

    # Add deduplication check using message timestamp
    thread_messages = handle_message.processed_messages.get(thread_ts, set())
    if message_ts in thread_messages:
        logger.info(f"Skipping duplicate message {message_ts} in thread {thread_ts}")
        return
    # Store message as processed
    if thread_ts not in handle_message.processed_messages:
        handle_message.processed_messages[thread_ts] = set()
    handle_message.processed_messages[thread_ts].add(message_ts)

    logger.info(f"Received message from user {user} in channel {channel}")

    # Check if bot should respond
    tagged_in_parent = False
    if thread_ts:
        parent_message = client.conversations_replies(
            channel=channel, ts=thread_ts, limit=1
        )["messages"][0]
        tagged_in_parent = f"<@{bot_user_id}>" in parent_message.get("text", "")

    should_respond = (
        channel_type == "im"
        or f"<@{bot_user_id}>" in message.get("text", "")
        or tagged_in_parent
    )

    if not should_respond:
        logger.info("Skipping message")
        return

    conversation = get_conversation_history(client, channel, thread_ts, bot_user_id)
    logger.info(f"Got conversation history with {len(conversation)} messages")

    try:
        # Use ChatService to handle the message based on user's mode
        result = ChatService.handle_user_message(
            user_id=user,
            channel_id=channel,
            thread_ts=thread_ts,
            message_text=message.get("text", ""),
            conversation=conversation
        )
        
        mode = result.get("mode")
        responses = result.get("responses", [])
        metadata = result.get("metadata", {})
        
        logger.info(f"ChatService returned mode: {mode}, {len(responses)} responses")
        
        if mode == "chat_mode":
            # Single persona response
            if responses:
                response = responses[0]
                response_text = f"<@{user}> {response['text']}"
                
                if channel_type == "im":
                    client.chat_postMessage(text=response_text, channel=channel)
                else:
                    client.chat_postMessage(text=response_text, channel=channel, thread_ts=thread_ts)
                    
                logger.info(f"Sent chat mode response using persona: {response.get('persona_name')}")
        
        elif mode == "ab_testing":
            # A/B testing responses
            if len(responses) >= 2:
                # Send intro message
                intro_text = f"<@{user}> {metadata.get('intro_message', 'Here are two responses:')}"
                
                if channel_type == "im":
                    client.chat_postMessage(text=intro_text, channel=channel)
                    
                    # Send response A
                    resp_a = client.chat_postMessage(
                        channel=channel,
                        **responses[0]['slack_message']
                    )
                    
                    # Send response B  
                    resp_b = client.chat_postMessage(
                        channel=channel,
                        **responses[1]['slack_message']
                    )
                    
                else:
                    client.chat_postMessage(text=intro_text, channel=channel, thread_ts=thread_ts)
                    
                    # Send response A in thread
                    resp_a = client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        **responses[0]['slack_message']
                    )
                    
                    # Send response B in thread
                    resp_b = client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        **responses[1]['slack_message']
                    )
                
                logger.info(f"Sent A/B testing responses for test {metadata.get('ab_test_id')}")
        
        else:
            # Fallback or error mode
            if responses:
                response_text = f"<@{user}> {responses[0].get('text', 'Sorry, something went wrong.')}"
                
                if channel_type == "im":
                    client.chat_postMessage(text=response_text, channel=channel)
                else:
                    client.chat_postMessage(text=response_text, channel=channel, thread_ts=thread_ts)
        
    except Exception as e:
        logger.error(f"Error handling message with ChatService: {e}")
        # Ultimate fallback
        try:
            claude_reply = get_standard_claude_response(conversation)
            response_text = f"<@{user}> {claude_reply}"
            
            if channel_type == "im":
                client.chat_postMessage(text=response_text, channel=channel)
            else:
                client.chat_postMessage(text=response_text, channel=channel, thread_ts=thread_ts)
                
            logger.info("Sent fallback response")
        except Exception as fallback_e:
            logger.error(f"Even fallback failed: {fallback_e}")


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
    
    elif action_id in ["set_active_persona", "switch_to_chat_mode"]:
        return handle_chat_mode_actions(payload, action)
    
    # Handle persona management actions
    elif action_id in ["view_personas", "create_persona", "view_analytics"]:
        return handle_persona_management(payload, action)
    
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
    """Handle A/B persona selections."""
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
            logger.info(f"Updated {response_key} persona to {persona_id} for user {user_id}")
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling A/B persona selection: {e}")
        return jsonify({"error": "Failed to update persona"}), 500


def handle_chat_persona_selection(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle chat persona selection."""
    try:
        user_id = payload.get("user", {}).get("id")
        persona_id = action.get("selected_option", {}).get("value")
        
        if not all([user_id, persona_id]):
            return jsonify({"error": "Missing data"}), 400
        
        # Update active persona (but don't switch mode automatically)
        success = PersonaManager.set_active_persona(user_id, int(persona_id))
        
        if success:
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


def handle_chat_mode_actions(payload: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """Handle chat mode related actions."""
    try:
        user_id = payload.get("user", {}).get("id")
        action_id = action.get("action_id")
        
        if action_id == "switch_to_chat_mode":
            # Switch to chat mode
            success = ChatService.set_user_mode(user_id, "chat_mode")
            
            if success:
                # Update home tab
                view = update_home_tab_with_user_data(user_id)
                safe_publish_home_tab(user_id, view)
                
                # Send confirmation
                slack_client.chat_postMessage(
                    channel=user_id,
                    text="✅ Switched to Chat Mode! You'll now chat with your active persona. Use the home tab to switch personas anytime."
                )
                
                logger.info(f"Switched user {user_id} to chat mode")
        
        elif action_id == "set_active_persona":
            # This just confirms the current selection
            slack_client.chat_postMessage(
                channel=user_id,
                text="✅ Active persona confirmed! Switch to Chat Mode to start using it."
            )
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling chat mode action: {e}")
        return jsonify({"error": "Failed to process action"}), 500


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


def handle_modal_submission(payload: Dict[str, Any]) -> Any:
    """Handle modal form submissions."""
    try:
        view = payload.get("view", {})
        callback_id = view.get("callback_id")
        user_id = payload.get("user", {}).get("id")
        
        if callback_id == "create_persona":
            return handle_create_persona_submission(payload, user_id)
        
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
        model = values.get("ai_model", {}).get("model_select", {}).get("selected_option", {}).get("value")
        temperature = float(values.get("temperature", {}).get("temperature_select", {}).get("selected_option", {}).get("value", "0.7"))
        
        # System prompt handling
        prompt_selection = values.get("system_prompt_selector", {}).get("prompt_select", {}).get("selected_option", {})
        prompt_content = values.get("system_prompt_content", {}).get("prompt_input", {}).get("value", "").strip()
        
        # Prompt saving options
        save_prompt_checked = values.get("system_prompt_content", {}).get("save_prompt_checkbox", {}).get("selected_options", [])
        save_new_prompt = len(save_prompt_checked) > 0
        new_prompt_title = values.get("new_prompt_title", {}).get("prompt_title_input", {}).get("value", "").strip()
        
        # Validate required fields
        if not all([persona_name, model, prompt_content]):
            return jsonify({
                "response_action": "errors",
                "errors": {
                    "persona_name": "Persona name is required" if not persona_name else "",
                    "ai_model": "Model selection is required" if not model else "",
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
    logger.error(f"Database Error [{error_id}]: {e}")
    
    # Track database error
    track_error("database_error", str(e), error_id)
    
    # For Slack API endpoints, return 200 to prevent retries
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
                    text="🔧 I'm experiencing database connectivity issues. Please try again in a moment."
                )
        except Exception as slack_error:
            logger.error(f"Failed to send database error message to Slack: {slack_error}")
        
        return jsonify({"status": "ok", "message": "Database temporarily unavailable"}), 200
    
    return jsonify({
        "error": "Database unavailable",
        "error_id": error_id,
        "message": "Database is temporarily unavailable. Please try again later."
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

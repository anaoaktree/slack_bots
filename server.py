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
    get_creative_claude_response,
    get_standard_claude_response,
    ABTestingService,
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
with app.app_context():
    db.create_all()

def load_json_view(file_name: str) -> Dict[str, Any]:
    """Load JSON view file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, "views", f"{file_name}.json")
    with open(json_path, "r") as file:
        return json.load(file)


# Event Handlers
# @app.event("app_home_opened")
def update_home_tab(
    client: Any, event: Dict[str, Any], logger: logging.Logger, ack: Any
) -> None:
    """Handle home tab opening."""
    ack()
    try:
        view = load_json_view("app_home")
        client.views_publish(user_id=event["user"], view=view)
    except Exception as e:
        logger.error(f"Error publishing home tab: {e}")


# @app.action("save_settings")
def handle_save_settings(
    ack: Any, body: Dict[str, Any], logger: logging.Logger
) -> None:
    """Handle settings save action."""
    # TODO
    ack()
    logger.info(body)
# https://tools.slack.dev/node-slack-sdk/tutorials/local-development/
# https://api.slack.com/apis/events-api
@app.route("/event", methods=["POST"])
def slack_event_handler():
    # Get the JSON payload
    payload = request.get_json()
    # TODO: check how to make logger appear in pythonanywhere
    logger.info(f"Received Slack event payload: {payload}")

    # Handle Slack URL verification
    if payload.get("type") == "url_verification":
        return jsonify({"challenge": payload["challenge"]})

    # Handle other events
    event = payload.get("event", {})
    event_type = event.get("type")
    if event_type in ["app_mention", "message"]:
        handle_message(event, slack_client)
    
    logger.info(f"Received Slack event type: {event_type}")

    # TODO: Add your event handling logic here
    # check making it async https://blog.pythonanywhere.com/198/
    
    # Return a 200 OK response to acknowledge receipt
    return jsonify({"status": "ok"})


"""
app mention in channel
{#012  "token": "M7DmOFh0DnEEuxRl3H0tzsW9",#012  "team_id": "T089B7235HT",#012  "api_app_id": "A08E17BK8H1",#012  "event": {#012    "user": "U089E23JSJE",#012    "type": "app_mention",#012    "ts": "1739981038.601839",#012    "client_msg_id": "9384d2e3-8e79-47d8-affe-5b946e405acb",#012    "text": "<@U08E1KS5EKU> testing one two three",#012    "team": "T089B7235HT",#012    "blocks": [#012      {#012        "type": "rich_text",#012        "block_id": "e066k",#012        "elements": [#012          {#012            "type": "rich_text_section",#012            "elements": [#012              {#012                "type": "user",#012                "user_id": "U08E1KS5EKU"#012              },#012              {#012                "type": "text",#012                "text": " testing one two three"#012              }#012            ]#012          }#012        ]#012      }#012    ],#012    "channel": "C08A2S74EKS",#012    "event_ts": "1739981038.601839"#012  },#012  "type": "event_callback",#012  "event_id": "Ev08DM9EK56


message in thread (no mention)
Received Slack event payload: {#012  "token": "M7DmOFh0DnEEuxRl3H0tzsW9",#012  "team_id": "T089B7235HT",#012  "context_team_id": "T089B7235HT",#012  "context_enterprise_id": null,#012  "api_app_id": "A08E17BK8H1",#012  "event": {#012    "user": "U089E23JSJE",#012    "type": "message",#012    "ts": "1739981735.396829",#012    "client_msg_id": "5a1863d5-a8ec-453b-973f-6c85cfb97930",#012    "text": "Hey what is happening",#012    "team": "T089B7235HT",#012    "thread_ts": "1739981038.601839",#012    "parent_user_id": "U089E23JSJE",#012    "blocks": [#012      {#012        "type": "rich_text",#012        "block_id": "JxKan",#012        "elements": [#012          {#012            "type": "rich_text_section",#012            "elements": [#012              {#012                "type": "text",#012                "text": "Hey what is happening"#012              }#012            ]#012          }#012        ]#012      }#012    ],#012    "channel": "C08A2S74EKS",#012    "event_ts": "1739981735.396829",#012    "channel_type": "channel"#012  },#012  "ty

# message in thread with mention
{#012  "token": "M7DmOFh0DnEEuxRl3H0tzsW9",#012  "team_id": "T089B7235HT",#012  "api_app_id": "A08E17BK8H1",#012  "event": {#012    "user": "U089E23JSJE",#012    "type": "app_mention",#012    "ts": "1739981950.771599",#012    "client_msg_id": "99d82487-2ce6-44d4-8575-a79c3f84beb4",#012    "text": "<@U08E1KS5EKU> message sent in thread with a mention",#012    "team": "T089B7235HT",#012    "thread_ts": "1739981038.601839",#012    "parent_user_id": "U089E23JSJE",#012    "blocks": [#012      {#012        "type": "rich_text",#012        "block_id": "r8Ac7",#012        "elements": [#012          {#012            "type": "rich_text_section",#012            "elements": [#012              {#012                "type": "user",#012                "user_id": "U08E1KS5EKU"#012              },#012              {#012                "type": "text",#012                "text": " message sent in thread with a mention"#012              }#012            ]#012          }#012        ]#012      }#012    ],#012    "channel": "C0

message in channel (no mention)
{#012  "token": "M7DmOFh0DnEEuxRl3H0tzsW9",#012  "team_id": "T089B7235HT",#012  "context_team_id": "T089B7235HT",#012  "context_enterprise_id": null,#012  "api_app_id": "A08E17BK8H1",#012  "event": {#012    "user": "U089E23JSJE",#012    "type": "message",#012    "ts": "1739981963.188539",#012    "client_msg_id": "849168a0-6f73-4a08-aa1e-c23bb1b4a3a9",#012    "text": "Message sent in channel with no mention",#012    "team": "T089B7235HT",#012    "blocks": [#012      {#012        "type": "rich_text",#012        "block_id": "juN4A",#012        "elements": [#012          {#012            "type": "rich_text_section",#012            "elements": [#012              {#012                "type": "text",#012                "text": "Message sent in channel with no mention"#012              }#012            ]#012          }#012        ]#012      }#012    ],#012    "channel": "C08A2S74EKS",#012    "event_ts": "1739981963.188539",#012    "channel_type": "channel"#012  },#012  "type": "event_callback",#012  "event_id": "E
"""

# TODO:
def handle_message(message: Dict[str, Any], client: WebClient) -> None:
    # Initialize processed messages dict if it doesn't exist - TODO move this to a db
    if not hasattr(handle_message, 'processed_messages'):
        handle_message.processed_messages = {}

    """Handle incoming messages."""
    bot_user_id = client.auth_test()["user_id"]
    user = message.get("user")
    
    # Ignoreif the message is from the bot itself
    if user == bot_user_id:
        logger.info("Skipping bot's own message")
        return

    channel_type = message.get("channel_type") 
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    message_ts = message.get("ts")

    # Add deduplication check using message timestamp. Check if message was already processed in this thread TODO: move this to a db
    thread_messages = handle_message.processed_messages.get(thread_ts, set())
    if message_ts in thread_messages:
        logger.info(f"Skipping duplicate message {message_ts} in thread {thread_ts}")
        return
    # Store message as processed
    if thread_ts not in handle_message.processed_messages:
        handle_message.processed_messages[thread_ts] = set()
    handle_message.processed_messages[thread_ts].add(message_ts)

    logger.info(f"Received message from user {user} in channel {channel} with id {message.get('id')}")
    logger.info(f"Message {message}")

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
    logger.info(f"conversation {conversation}")

    # TODO: add a flag to use A/B testing or not
    # claude_reply = get_standard_claude_response(conversation)

    # response_text = f"<@{user}>{claude_reply}"
    # if channel_type == "im":
    #     logger.info(f"Successfully sent response to user {user}")
    #     client.chat_postMessage(text=response_text, channel=channel)
    # else:
    #     client.chat_postMessage(text=response_text, channel=channel, thread_ts=thread_ts)

    # A/B testing starts here
    try:
        # Create A/B test with two different responses
        ab_test, response_a, response_b = ABTestingService.create_ab_test_responses(
            user_id=user,
            channel_id=channel,
            thread_ts=thread_ts,
            original_prompt=message.get("text", ""),
            conversation=conversation
        )
        
        # Create Slack messages with voting buttons
        message_a = ABTestingService.create_slack_message_with_buttons(
            response_text=response_a.response_text,
            variant="A",
            test_id=ab_test.id,
            user_id=user
        )
        
        message_b = ABTestingService.create_slack_message_with_buttons(
            response_text=response_b.response_text,
            variant="B", 
            test_id=ab_test.id,
            user_id=user
        )
        
        # Send both responses
        if channel_type == "im":
            # Send intro message
            client.chat_postMessage(
                text=f"<@{user}> Here are two different responses to your question. Please vote for the one you prefer!",
                channel=channel
            )
            
            # Send response A
            resp_a = client.chat_postMessage(
                channel=channel,
                **message_a
            )
            
            # Send response B  
            resp_b = client.chat_postMessage(
                channel=channel,
                **message_b
            )
            
        else:
            # Send intro message in thread
            client.chat_postMessage(
                text=f"<@{user}> Here are two different responses to your question. Please vote for the one you prefer!",
                channel=channel,
                thread_ts=thread_ts
            )
            
            # Send response A in thread
            resp_a = client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                **message_a
            )
            
            # Send response B in thread
            resp_b = client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                **message_b
            )
        
        # Update database with Slack message timestamps
        response_a.slack_message_ts = resp_a["ts"]
        response_b.slack_message_ts = resp_b["ts"]
        db.session.commit()
        
        logger.info(f"Successfully sent A/B test responses for user {user}")
        
    except Exception as e:
        logger.error(f"Error in A/B testing: {e}")
        # Fallback to standard response
        claude_reply = get_standard_claude_response(conversation)
        response_text = f"<@{user}> {claude_reply}"
        
        if channel_type == "im":
            client.chat_postMessage(text=response_text, channel=channel)
        else:
            client.chat_postMessage(text=response_text, channel=channel, thread_ts=thread_ts)

# TODO
# @app.command("/creative-gp")
def handle_creative_gp(ack: Any, body: Dict[str, Any], client: Any, say: Any) -> None:
    """Handle creative GP command."""
    user_id = body.get("user_id")
    logger.info(f"Received creative-gp command from user {user_id}")
    logger.debug(f"Command body: {body}")
    ack()

    try:
        bot_id = client.auth_test()["user_id"]
        response = say(
            token=os.environ["USER_AUTH_TOKEN"],
            text=f"<@{bot_id}> {body['text']}",
            user=user_id,
        )

        conversation = get_conversation_history(
            client, body["channel_id"], response["ts"], bot_id
        )
        claude_reply = get_creative_claude_response(conversation)

        client.chat_postMessage(
            channel=body["channel_id"],
            text=f"[CREATIVE MODE] {claude_reply}",
            thread_ts=response["ts"],
        )

    except Exception as e:
        logger.error(f"Error in creative-gp command: {str(e)}")
        say(text=f"Sorry, an error occurred: {str(e)} for your message: {body['text']}")

@app.route("/", methods=["GET"])
def hello():
    return "<html><body><h1>Hello World</h1></body></html>"

@app.route("/interactive", methods=["POST"])
def handle_interactive_component():
    """Handle Slack interactive components like button clicks."""
    payload = json.loads(request.form.get("payload"))
    logger.info(f"Received interactive payload: {payload}")
    
    # Extract action information
    actions = payload.get("actions", [])
    if not actions:
        return jsonify({"status": "ok"})
    
    action = actions[0]
    action_id = action.get("action_id")
    
    # Handle voting actions
    if action_id in ["vote_a", "vote_b"]:
        return handle_ab_vote(payload, action)
    
    return jsonify({"status": "ok"})


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
        
        confirmation_text = f"<@{user_id}> Thanks for your feedback! You voted for Response {variant}."
        
        slack_client.chat_postMessage(
            channel=channel_id,
            text=confirmation_text,
            thread_ts=payload.get("message", {}).get("thread_ts")
        )
        
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error handling A/B vote: {e}")
        return jsonify({"error": "Failed to process vote"}), 500

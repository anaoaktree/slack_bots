import json
import os
import ssl
from typing import Any, Dict
import logging

import certifi
from dotenv import load_dotenv
from slack_sdk import WebClient
from flask import Flask, jsonify, request
from services import (
    get_conversation_history,
    get_creative_claude_response,
    get_standard_claude_response,
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
slack_client = WebClient(token=os.environ["CHACHIBT_APP_BOT_AUTH_TOKEN"])


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
@app.route("/event", methods=["POST"])
def slack_event_handler():
    # Get the JSON payload
    payload = request.get_json()
    # TODO: check how to make logger appear in pythonanywhere
    logger.info(f"Received Slack event payload: {json.dumps(payload, indent=2)}")

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
    """Handle incoming messages."""
    channel_type = message.get("channel_type") 
    bot_user_id = client.auth_test()["user_id"]
    user = message.get("user")
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    logger.info(f"Received message from user {user} in channel {channel} with id {message.get('id')}")
    logger.info(f"Message {message}")

    # Check if bot should respond
    tagged_in_parent = False
    if thread_ts:
        parent_message = client.conversations_replies(
            channel=channel, ts=thread_ts, limit=1
        )["messages"][0]
        tagged_in_parent = f"<@{bot_user_id}>" in parent_message.get("text", "")

    if not (
        channel_type == "im"
        or f"<@{bot_user_id}>" in message.get("text", "")
        or tagged_in_parent
    ):
        logger.info("Skipping message")
        return

    conversation = get_conversation_history(client, channel, thread_ts, bot_user_id)
    logger.info(f"conversation {conversation}")

    claude_reply = get_standard_claude_response(conversation)

    response_text = f"<@{user}>{claude_reply}"
    if channel_type == "im":
        logger.info(f"Successfully sent response to user {user}")
        client.chat_postMessage(text=response_text)
    else:
        client.chat_postMessage(text=response_text, thread_ts=thread_ts)

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

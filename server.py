import json
import os
import ssl
from typing import Any, Dict, Optional

import certifi
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

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

# TODO make it async https://tools.slack.dev/bolt-python/concepts/async
# App Initialization
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)


def load_json_view(file_name: str) -> Dict[str, Any]:
    """Load JSON view file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, "views", f"{file_name}.json")
    with open(json_path, "r") as file:
        return json.load(file)


# Event Handlers
@app.event("app_home_opened")
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


@app.action("save_settings")
def handle_save_settings(
    ack: Any, body: Dict[str, Any], logger: logging.Logger
) -> None:
    """Handle settings save action."""
    # TODO
    ack()
    logger.info(body)


@app.event("message")
def handle_message(message: Dict[str, Any], say: Any, client: Any, ack: Any) -> None:
    """Handle incoming messages."""
    channel_type = message.get("channel_type")
    bot_user_id = client.auth_test()["user_id"]
    user = message.get("user")
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    logger.info(f"Received message from user {user} in channel {
        channel} with id {message['client_msg_id']}")
    logger.info(f"Message {message}")
    ack()

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
        say(response_text)
    else:
        say(text=response_text, thread_ts=thread_ts)


@app.command("/creative-gp")
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
        print(f"Error in creative-gp command: {str(e)}")
        say(text=f"Sorry, an error occurred: {str(e)} for your message: {body['text']}")


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()

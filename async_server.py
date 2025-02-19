import json
import os
import ssl
from typing import Any, Dict
import logging

import certifi
from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from services import (
    async_conversation_history,
    async_standard_claude_response,
)
from utils import setup_logger

# SSL and Environment Configuration
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context
load_dotenv()

logger = setup_logger(__name__)

# Initialize AsyncApp
app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

async def load_json_view(file_name: str) -> Dict[str, Any]:
    """Load JSON view file."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, "views", f"{file_name}.json")
    with open(json_path, "r") as file:
        return json.load(file)

@app.event("app_home_opened")
async def update_home_tab(client: Any, event: Dict[str, Any], logger: logging.Logger):
    """Handle home tab opening."""
    try:
        view = await load_json_view("app_home")
        await client.views_publish(user_id=event["user"], view=view)
    except Exception as e:
        logger.error(f"Error publishing home tab: {e}")

@app.action("save_settings")
async def handle_save_settings(ack: Any, body: Dict[str, Any], logger: logging.Logger):
    """Handle settings save action."""
    await ack()
    logger.info(body)

@app.event("message")
async def handle_message(message: Dict[str, Any], say: Any, client: Any):
    """Handle incoming messages."""
    channel_type = message.get("channel_type")
    bot_user_id = (await client.auth_test())["user_id"]
    user = message.get("user")
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    
    # Check if bot should respond
    tagged_in_parent = False
    if thread_ts:
        parent_message = (await client.conversations_replies(
            channel=channel, ts=thread_ts, limit=1
        ))["messages"][0]
        tagged_in_parent = f"<@{bot_user_id}>" in parent_message.get("text", "")

    if not (
        channel_type == "im"
        or f"<@{bot_user_id}>" in message.get("text", "")
        or tagged_in_parent
    ):
        return

    conversation = await async_conversation_history(client, channel, thread_ts, bot_user_id)
    claude_reply = await async_standard_claude_response(conversation)

    response_text = f"<@{user}>{claude_reply}"
    if channel_type == "im":
        await say(response_text)
    else:
        await say(text=response_text, thread_ts=thread_ts)

async def main():
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

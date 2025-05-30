import re
import base64
from typing import Dict, List, Optional, Tuple
import requests

from utils import setup_logger

logger = setup_logger(__name__)


def clean_user_mentions(text: str) -> str:
    """Remove user mentions from text."""
    return re.sub(r"<@[A-Z0-9]+>", "", text).strip()


def get_thread_history(client, channel: str, thread_ts: str) -> List[Dict]:
    """Fetch thread history from Slack."""
    messages = []
    cursor = None
    while True:
        try:
            result = client.conversations_replies(
                channel=channel, ts=thread_ts, cursor=cursor, limit=100
            )
            messages.extend(result["messages"])
            if not result.get("has_more", False):
                break
            cursor = result["response_metadata"]["next_cursor"]
        except Exception as e:
            logger.error(f"Error fetching thread history: {e}")
            break
    return messages


def get_conversation_history(
    client, channel: str, thread_ts: str, bot_user_id: str
) -> List[Dict]:
    """Convert Slack thread history to Claude conversation format."""
    conversation = []
    messages = get_thread_history(client, channel, thread_ts)


    for i, msg in enumerate(messages):
        role = "assistant" if msg.get("user") == bot_user_id else "user"
        msg_text = clean_user_mentions(msg["text"])
        msg_ts = msg.get("ts", "unknown")
        msg_user = msg.get("user", "unknown")
        
        logger.info(f"RAW_MSG[{i}]: user={msg_user}, role={role}, ts={msg_ts}, text='{msg_text[:50]}{'...' if len(msg_text) > 50 else ''}'")
        
        content = []

        # Handle any files in the message
        files = msg.get('files', [])
        for file in files:
            if _is_valid_pdf(file):
                try:
                    response = client.files_info(file=file['id'])
                    url = response['file']['url_private']
                    headers = {'Authorization': f'Bearer {client.token}'}
                    response = requests.get(url, headers=headers)
                    file_content = base64.b64encode(response.content).decode('utf-8')
                    
                    content.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": file_content
                        },
                        "citations": {"enabled": True}
                    })
                except Exception as e:
                    logger.error(f"Error processing file {file.get('name')}: {str(e)}")

        # Add text content if present
        if msg_text:
            content.append({"type": "text", "text": msg_text})
            conversation.append({"role": role, "content": content})


    return conversation

# TODO: add Max page count and make sure it applies to all files
def _is_valid_pdf(file: Dict) -> bool:
    """
    Validate if file is a PDF and meets Claude's requirements:
    - Must be PDF
    - Must be under 32MB
    """
    MAX_SIZE_MB = 32
    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    
    is_pdf = file.get('mimetype') == 'application/pdf'
    size_ok = file.get('size', float('inf')) <= MAX_SIZE_BYTES
    
    return is_pdf and size_ok

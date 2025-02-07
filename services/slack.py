from typing import List, Dict
import re
from utils import setup_logger

logger = setup_logger(__name__)


def clean_user_mentions(text: str) -> str:
    """Remove user mentions from text."""
    return re.sub(r'<@[A-Z0-9]+>', '', text).strip()


def get_thread_history(
    client,
    channel: str,
    thread_ts: str
) -> List[Dict]:
    """Fetch thread history from Slack."""
    messages = []
    cursor = None
    while True:
        try:
            result = client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                cursor=cursor,
                limit=100
            )
            messages.extend(result['messages'])
            if not result.get('has_more', False):
                break
            cursor = result['response_metadata']['next_cursor']
        except Exception as e:
            print(f"Error fetching thread history: {e}")
            break
    return messages



def get_conversation_history(
        client,
        channel: str,
        thread_ts: str,
        bot_user_id: str
    ) -> List[Dict]:
        """Convert Slack thread history to Claude conversation format."""
        conversation = []
        messages = get_thread_history(client, channel, thread_ts)

        for msg in messages:
            role = 'assistant' if msg.get('user') == bot_user_id else 'user'
            msg_text = clean_user_mentions(msg['text'])
            logger.info(f"MSG INSIDE GET CONVO HIST {msg['ts']}")

            conversation.append({
                'role': role,
                'content': [{"type": "text", "text": msg_text}]
            })
        
        return conversation
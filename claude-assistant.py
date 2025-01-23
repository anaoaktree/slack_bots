import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import anthropic
from typing import List, Dict
import ssl
import certifi

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context

load_dotenv()

# TODO make it async https://tools.slack.dev/bolt-python/concepts/async
# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ.get("SLACK_BOT_TOKEN"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"))
claude = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY"))

haiku = "claude-3-5-haiku-latest"
sonnet = "claude-3-5-sonnet-latest"

def get_claude_creative_response(conversation: List[Dict]):
    """
    Calls anthropic API to generate text.
    """
    claude_message = claude.messages.create(
        model=haiku,
        temperature=1,
        max_tokens=2000,
        system= open('prompts/gp-creative.txt', 'r').read(),
        messages=conversation
    )
    return claude_message.content[0].text



def get_claude_response(conversation: List[Dict]) -> str:
    """
    Calls anthropic API to generate text.
    """
    claude_message = claude.messages.create(
        model=sonnet,
        max_tokens=2000,
        system= open('prompts/assistant_prompt.txt', 'r').read(),
        messages=conversation
    )
    return claude_message.content[0].text


def get_thread_history(client, channel, thread_ts):
    messages = []
    cursor = None
    
    while True:
        try:
            result = client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                cursor=cursor,
                limit=100  # Adjust as needed
            )
            messages.extend(result['messages'])
            
            # Check if there are more messages
            if not result.get('has_more', False):
                break
                
            cursor = result['response_metadata']['next_cursor']
            
        except Exception as e:
            print(f"Error fetching thread history: {e}")
            break
    
    return messages


import re

# Function to clean message text of all user mentions
def clean_user_mentions(text):
    """
    Removes all user mentions in the format <@USERID> from text
    Returns the cleaned text
    """
    return re.sub(r'<@[A-Z0-9]+>', '', text).strip()


def get_conversation_from_history(client, channel, thread_ts, bot_user_id):
        # Get thread history if this is a thread message
    conversation = []
    messages = get_thread_history(client, channel, thread_ts)

    # Convert thread messages to Claude format
    for thread_msg in messages:
        # Skip bot's own messages when building history
        if thread_msg.get('user') == bot_user_id:
            role = 'assistant'
        else:
            role = 'user'

        # Remove user mention from messages
        msg_text = clean_user_mentions(thread_msg['text'])
        # .replace(f'<@{bot_user_id}>', '').strip()
        
        conversation.append({
            'role': role,
            'content': [{"type": "text", "text": msg_text}]
        })
    return conversation

import json
def load_json_view(file_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, 'views', f"{file_name}.json")
    
    with open(json_path, 'r') as file:
        return json.load(file)

@app.event("app_home_opened")
def update_home_tab(client, event, logger):
    try:
        # Create the view using Block Kit
        view = load_json_view("app_home")
        # Publish the view
        client.views_publish(
                user_id=event["user"],
                view=view
            )
    except Exception as e:
            logger.error(f"Error publishing home tab: {e}")
            
# Handle the save button action
@app.action("save_settings")
def handle_some_action(ack, body, logger):
    ack()
    logger.info(body)
    print(body)



# Listens to incoming messages that contain "hello"
# To learn available listener arguments,
# visit https://tools.slack.dev/bolt-python/api-docs/slack_bolt/kwargs_injection/args.html
@app.event("message")
def message_hello(message, say, logger, client):
    print("RECEIVED MESSAGE")

    # 1. Check if bot should respond or ignore
    
    channel_type = message.get('channel_type')
    bot_user_id = client.auth_test()["user_id"]

    tagged_in_parent = False
    thread_ts = message.get('thread_ts', message.get('ts'))

    # Checks if bot should participate in this thread
    if thread_ts:
        # For threaded messages, check the parent message for bot mention
        parent_message = client.conversations_replies(
            channel=message['channel'],
            ts=thread_ts,
            limit=1  # We only need the first (parent) message
        )['messages'][0]
        tagged_in_parent = f'<@{bot_user_id}>' in parent_message.get('text', '')


    # Only proceed if:
    # 1. It's a DM (we always respond in DMs) OR
    # 2. The bot was mentioned (in a channel/group) OR
    # 3. The bot was mention on the first message of the thread
    if not (channel_type == 'im' or 
            f'<@{bot_user_id}>' in message.get('text', '') or 
            tagged_in_parent):
            print("SHOULD NOT PROCEED")
            return

    print("GETTING REPLY...")
    conversation = get_conversation_from_history(client, message['channel'], thread_ts, bot_user_id)
    claude_reply = get_claude_response(conversation)

    if channel_type == 'im':
        # For DMs, reply without thread
        # get response from claude LLM
        say(f"<@{message['user']}>{claude_reply}")
    else:
        # For channels and private channels, reply in thread
        say(
            text=f"<@{message['user']}>{claude_reply}",
            thread_ts=thread_ts
        )
@app.command("/creative-gp")
def handle_creative_gp(ack, body, client, say):
    print("RECEIVED COMMAND")
    ack()
    text = body['text']
    try:
        bot_id = client.auth_test()["user_id"]

        # Instead of just saying the message, post it as the user
        # This will trigger your message event handler
        # First message creates the thread
        # response = client.chat_postMessage(
        #     token=os.environ["USER_AUTH_TOKEN"],
        #     channel=body['channel_id'],
        #     text=f"<@{bot_id}> {text}",
        #     user=body['user_id']
        # )
        response = say(token=os.environ["USER_AUTH_TOKEN"] ,text=f"<@{bot_id}> {text}", user=body['user_id'])

        thread_ts = response['ts']

        print("GETTING CREATIVE REPLY...")
        conversation = get_conversation_from_history(client, body['channel_id'], thread_ts, bot_id)
        claude_reply = get_claude_creative_response(conversation)

        # Second message in thread
        client.chat_postMessage(
            channel=body['channel_id'],
            text=f"[CREATIVE MODE] {claude_reply}",
            thread_ts=response['ts']
        )
        # The message event handler will now process this message
        # because it contains the bot mention

    except Exception as e:
        print(f"Error in creative-gp command: {str(e)}")
        say(text=f"Sorry, an error occurred: {str(e)} for your message: {text}")


# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
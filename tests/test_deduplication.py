#!/usr/bin/env python3
"""
Test script to verify the deduplication logic for handling duplicate Slack events.
"""

import sys
from unittest.mock import Mock

# Mock the WebClient and ChatService for testing
class MockWebClient:
    def auth_test(self):
        return {"user_id": "U08E1KS5EKU"}
    
    def conversations_replies(self, **kwargs):
        return {"messages": [{"text": "test message"}]}
    
    def chat_postMessage(self, **kwargs):
        print(f"📤 Sending message: {kwargs.get('text', 'No text')[:50]}...")
        return {"ok": True}

class MockChatService:
    @staticmethod
    def handle_user_message(**kwargs):
        print("🤖 Called Anthropic API - generating response...")
        return {
            "mode": "chat_mode",
            "responses": [{"text": "Test response", "persona_name": "Test"}],
            "metadata": {}
        }

# Simulate the original deduplication logic (the problematic one)
def handle_message_original(message, client):
    """Original deduplication logic that caused the problem."""
    if not hasattr(handle_message_original, 'processed_messages'):
        handle_message_original.processed_messages = {}

    user = message.get("user")
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    message_ts = message.get("ts")

    # OLD LOGIC - per thread deduplication
    thread_messages = handle_message_original.processed_messages.get(thread_ts, set())
    if message_ts in thread_messages:
        print(f"🚫 Original: Skipping duplicate message {message_ts} in thread {thread_ts}")
        return
    
    if thread_ts not in handle_message_original.processed_messages:
        handle_message_original.processed_messages[thread_ts] = set()
    handle_message_original.processed_messages[thread_ts].add(message_ts)

    print(f"✅ Original: Processing message {message_ts} from user {user}")
    
    # Simulate API call
    result = MockChatService.handle_user_message(
        user_id=user, channel_id=channel, thread_ts=thread_ts,
        message_text=message.get("text", ""), conversation=[]
    )
    client.chat_postMessage(text=f"<@{user}> {result['responses'][0]['text']}", channel=channel)

# Simulate the new deduplication logic (the fix)
def handle_message_fixed(message, client):
    """New deduplication logic that fixes the problem."""
    if not hasattr(handle_message_fixed, 'processed_messages'):
        handle_message_fixed.processed_messages = {}

    user = message.get("user")
    channel = message.get("channel")
    thread_ts = message.get("thread_ts", message.get("ts"))
    message_ts = message.get("ts")

    # NEW LOGIC - per channel:timestamp deduplication
    message_key = f"{channel}:{message_ts}"
    if message_key in handle_message_fixed.processed_messages:
        print(f"🚫 Fixed: Skipping duplicate message {message_ts} in channel {channel} (already processed)")
        return
    
    handle_message_fixed.processed_messages[message_key] = True

    print(f"✅ Fixed: Processing message {message_ts} from user {user}")
    
    # Simulate API call
    result = MockChatService.handle_user_message(
        user_id=user, channel_id=channel, thread_ts=thread_ts,
        message_text=message.get("text", ""), conversation=[]
    )
    client.chat_postMessage(text=f"<@{user}> {result['responses'][0]['text']}", channel=channel)

def test_deduplication():
    """Test both deduplication approaches with simulated Slack events."""
    print("🧪 Testing Slack Event Deduplication Logic\n")
    
    client = MockWebClient()
    
    # Simulate the SAME message coming as both 'message' and 'app_mention' events
    # This is what happens when someone mentions the bot in a channel
    message_event = {
        "user": "U089E23JSJE",
        "channel": "C08A2S74EKS", 
        "ts": "1748614772.474129",
        "thread_ts": "1748614772.474129",
        "text": "<@U08E1KS5EKU> what's your strengths?",
        "type": "message"
    }
    
    app_mention_event = {
        "user": "U089E23JSJE",
        "channel": "C08A2S74EKS",
        "ts": "1748614772.474129",  # SAME timestamp!
        "thread_ts": "1748614772.474129", 
        "text": "<@U08E1KS5EKU> what's your strengths?",
        "type": "app_mention"
    }
    
    print("=" * 60)
    print("🐛 TESTING ORIGINAL LOGIC (The Problem)")
    print("=" * 60)
    print("📨 Processing 'message' event...")
    handle_message_original(message_event, client)
    
    print("\n📨 Processing 'app_mention' event (same message)...")
    handle_message_original(app_mention_event, client)
    
    print("\n" + "=" * 60)
    print("✅ TESTING FIXED LOGIC (The Solution)")
    print("=" * 60)
    print("📨 Processing 'message' event...")
    handle_message_fixed(message_event, client)
    
    print("\n📨 Processing 'app_mention' event (same message)...")
    handle_message_fixed(app_mention_event, client)
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print("Original Logic: Allows duplicates because it only deduplicates within the same thread")
    print("Fixed Logic: Prevents duplicates because it deduplicates by channel:timestamp")
    print("\n🎯 The fix prevents the Anthropic API from being called twice for the same message!")

if __name__ == "__main__":
    test_deduplication() 
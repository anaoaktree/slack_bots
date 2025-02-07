import os
from typing import Dict, List

import anthropic
from dotenv import load_dotenv

load_dotenv()


claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

haiku = "claude-3-5-haiku-latest"
sonnet = "claude-3-5-sonnet-latest"


def get_creative_claude_response(conversation: List[Dict]) -> str:
    """Generate creative text using Claude API."""
    # TODO: check if messages race condition is causing multiple api calls.
    # TODO: add logging
    claude_message = claude.messages.create(
        model=haiku,
        temperature=1,
        max_tokens=2000,
        system=open("prompts/gp-creative.txt", "r").read(),
        messages=conversation,
    )
    return claude_message.content[0].text


def get_standard_claude_response(conversation: List[Dict]) -> str:
    """Generate standard text using Claude API."""
    claude_message = claude.messages.create(
        model=sonnet,
        max_tokens=2000,
        system=open("prompts/assistant_prompt.txt", "r").read(),
        messages=conversation,
    )
    return claude_message.content[0].text

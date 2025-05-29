import os
from typing import Dict, List

import anthropic
from dotenv import load_dotenv
from utils import setup_logger

load_dotenv()

logger = setup_logger(__name__)

claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

haiku = "claude-3-5-haiku-20241022"
sonnet = "claude-sonnet-4-20250514"
opus = "claude-opus-4-20250514"


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
    
    # Handle potential multiple content blocks
    response = []
    for content in claude_message.content:
        if content.type != "text":
            continue
            
        response.append(content.text)
        
        # Log and add citations if present
        if hasattr(content, 'citations') and content.citations:
            logger.info(f"Citations found: {len(content.citations)} citations")
            citations = []
            for citation in content.citations:
                logger.debug(f"Citation details: {citation}")
                citations.append(
                    f"\t<cited_text>{citation.cited_text}</cited_text> "
                    f"(from {citation.document_title})"
                )
            # TODO: think if citations are needed
            # if citations:
            #     response.append("\n" + "\n".join(citations))
    
    return "\n".join(response)

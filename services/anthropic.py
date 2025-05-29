import os
from typing import Dict, List

import anthropic
from dotenv import load_dotenv
from utils import setup_logger

load_dotenv()

logger = setup_logger(__name__)

claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
}

def get_standard_claude_response(conversation: List[Dict], system_prompt: str|None=None, model_name: str|None=None, temperature: float=1.0, max_tokens: int=2000) -> str:
    """Generate standard text using Claude API."""
    system_prompt = system_prompt or open("prompts/assistant_prompt.txt", "r").read()
    model_name = MODELS[model_name] if model_name else MODELS["sonnet"]
    claude_message = claude.messages.create(
        model=model_name,
        max_tokens=max_tokens,
        system=system_prompt,
        temperature=temperature,
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
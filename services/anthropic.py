import os
from typing import Dict, List

import anthropic
from dotenv import load_dotenv
from utils import setup_logger

load_dotenv()

logger = setup_logger(__name__)

# Validate API key at startup
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    logger.error("CRITICAL: ANTHROPIC_API_KEY environment variable is not set!")
    logger.error("Please ensure your environment contains ANTHROPIC_API_KEY=your_api_key_here")

claude = anthropic.Anthropic(api_key=api_key)

MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
}

# Cache the default system prompt instead of reading file every time
_DEFAULT_SYSTEM_PROMPT = None

def _get_default_system_prompt() -> str:
    """Get default system prompt, loading from file only once."""
    global _DEFAULT_SYSTEM_PROMPT
    if _DEFAULT_SYSTEM_PROMPT is None:
        try:
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prompt_path = os.path.join(current_dir, "prompts", "assistant_prompt.txt")
            
            if os.path.exists(prompt_path):
                with open(prompt_path, "r") as file:
                    _DEFAULT_SYSTEM_PROMPT = file.read().strip()
                logger.info("Loaded default system prompt from file")
            else:
                logger.warning(f"Default prompt file not found: {prompt_path}")
                _DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant. Provide clear, accurate, and balanced responses. Be concise but thorough, and always aim to be genuinely helpful to the user."
                
        except Exception as e:
            logger.error(f"Error loading default prompt file: {e}")
            _DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant. Provide clear, accurate, and balanced responses. Be concise but thorough, and always aim to be genuinely helpful to the user."
    
    return _DEFAULT_SYSTEM_PROMPT

def get_standard_claude_response(conversation: List[Dict], system_prompt: str|None=None, model_name: str|None=None, temperature: float=1.0, max_tokens: int=2000) -> str | None:
    """Generate standard text using Claude API."""
    # Use cached default prompt instead of reading file every time
    system_prompt = system_prompt or _get_default_system_prompt()
    model_name = MODELS[model_name] if model_name else MODELS["sonnet"]
    
    # Check if conversation already ends with assistant response
    if conversation and conversation[-1].get("role") == "assistant":
        logger.warning(f"CONVERSATION_ALREADY_COMPLETE: Last message is from assistant!")
        logger.warning(f"This might indicate duplicate processing or conversation history timing issue")
        return None  # Return None to indicate no response needed
    
    # Check for empty conversation
    if not conversation:
        logger.error(f"EMPTY_CONVERSATION: No messages to process!")
        return "I didn't receive any messages to respond to."
    
    # Check for conversation with only assistant messages
    user_messages = [msg for msg in conversation if msg.get("role") == "user"]
    if not user_messages:
        logger.error(f"NO_USER_MESSAGES: Conversation has no user messages!")
        return "I don't see any user messages to respond to."

    try:
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
        
        final_response = "\n".join(response)
        
        # Log the response details
        logger.info(f"CLAUDE_RESPONSE: length={len(final_response)}, preview='{final_response[:100]}{'...' if len(final_response) > 100 else ''}'")
        
        if not final_response or final_response.strip() == "":
            logger.error(f"EMPTY_CLAUDE_RESPONSE: Claude returned empty response!")
            logger.error(f"Raw response blocks: {[block.text for block in claude_message.content if block.type == 'text']}")
        
        return final_response
        
    except anthropic.APIConnectionError as e:
        logger.error(f"Anthropic API connection error: {e}")
        logger.error(f"API Key status - Present: {bool(api_key)}, Prefix: {api_key[:10] if api_key else 'None'}...")
        logger.error("Troubleshooting: Check internet connection, API key validity, and Anthropic service status")
        raise Exception("Connection error") from e
    except anthropic.RateLimitError as e:
        logger.error(f"Anthropic API rate limit error: {e}")
        logger.error("Troubleshooting: You've exceeded the API rate limits. Wait and try again later.")
        raise Exception("Rate limit exceeded") from e
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        logger.error("Troubleshooting: Check API key permissions and model availability")
        raise Exception("API error") from e
    except Exception as e:
        logger.error(f"Unexpected error calling Anthropic API: {e}")
        logger.error(f"Request details: model={model_name}, conversation_length={len(conversation)}")
        logger.error(f"API Key status: Present={bool(api_key)}, Length={len(api_key) if api_key else 0}")
        raise Exception("API error") from e
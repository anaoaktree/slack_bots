import os
import traceback
from typing import Dict, List, Optional, Tuple
from models import db, UserPreferences
from services.persona_manager import PersonaManager
from services.ab_testing import ABTestingService
from services.anthropic import get_standard_claude_response
from utils import setup_logger

logger = setup_logger(__name__)


class ChatService:
    """Service for handling chat interactions in both A/B testing and chat mode."""
    
    @staticmethod
    def get_user_mode(user_id: str) -> str:
        """Get the user's preferred mode (chat_mode or ab_testing)."""
        try:
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            if user_prefs and not user_prefs.chat_mode_enabled:
                return "ab_testing"
            return "chat_mode"  # Default to chat mode
        except Exception as e:
            logger.error(f"Error getting user mode for {user_id}: {e}")
            return "chat_mode"  # Default to chat mode on error
    
    @staticmethod
    def set_user_mode(user_id: str, mode: str) -> bool:
        """Set the user's preferred mode."""
        try:
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            if not user_prefs:
                user_prefs = UserPreferences(user_id=user_id)
                db.session.add(user_prefs)
            
            user_prefs.chat_mode_enabled = (mode == "chat_mode")
            db.session.commit()
            
            logger.info(f"Set mode to {mode} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting user mode for {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def handle_user_message(user_id: str, channel_id: str, thread_ts: str, 
                          message_text: str, conversation: List[Dict]) -> Dict | None:
        """
        Handle a user message and return appropriate response(s) based on mode.
        
        Returns:
            Dict with keys:
                - mode: "chat_mode" or "ab_testing"
                - responses: List of response dictionaries
                - metadata: Additional info about the response
        """
        try:
            mode = ChatService.get_user_mode(user_id)
            
            if mode == "chat_mode":
                return ChatService._handle_chat_mode(user_id, channel_id, thread_ts, message_text, conversation)
            else:
                return ChatService._handle_ab_testing_mode(user_id, channel_id, thread_ts, message_text, conversation)
                
        except Exception as e:
            # Enhanced error logging
            error_details = {
                "user_id": user_id,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "message_length": len(message_text) if message_text else 0,
                "conversation_length": len(conversation) if conversation else 0,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "anthropic_api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "anthropic_api_key_prefix": os.environ.get("ANTHROPIC_API_KEY", "")[:10] if os.environ.get("ANTHROPIC_API_KEY") else "None"
            }
            
            # Log full error details
            logger.error(f"CRITICAL ERROR handling message for user {user_id}: {e}")
            logger.error(f"Error Details: {error_details}")
            logger.error(f"Full Traceback:\n{traceback.format_exc()}")
            
            # Fallback to simple response in chat mode (default behavior)
            return {
                "mode": "chat_mode",
                "responses": [{
                    "text": "Sorry, I encountered an error processing your message. Please try again.",
                    "type": "error"
                }],
                "metadata": {"error": str(e), "error_details": error_details}
            }
    
    @staticmethod
    def _handle_chat_mode(user_id: str, channel_id: str, thread_ts: str, 
                         message_text: str, conversation: List[Dict]) -> Dict | None:
        """Handle message in chat mode using active persona."""
        try:
            # Get active persona
            active_persona = PersonaManager.get_active_persona(user_id)
            
            if not active_persona:
                # Create default personas if none exist
                PersonaManager._ensure_default_personas(user_id)
                active_persona = PersonaManager.get_active_persona(user_id)
            
            if not active_persona:
                raise Exception("Unable to create or find active persona")
            
            # Increment usage count for the persona
            PersonaManager.increment_usage(user_id, active_persona['id'])
            
            # Generate response using persona settings
            response_text = get_standard_claude_response(
                conversation,
                system_prompt=active_persona['system_prompt'], 
                temperature=active_persona['temperature'],
                model_name=active_persona['model']
            )
            
            if not response_text:
                return None
            
            return {
                "mode": "chat_mode",
                "responses": [{
                    "text": response_text,
                    "type": "persona_response",
                    "persona_name": active_persona['name'],
                    "persona_id": active_persona['id']
                }],
                "metadata": {
                    "active_persona": active_persona,
                    "usage_incremented": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error in chat mode for user {user_id}: {e}")
            raise e
    
    @staticmethod
    def _handle_ab_testing_mode(user_id: str, channel_id: str, thread_ts: str,
                               message_text: str, conversation: List[Dict]) -> Dict | None:
        """Handle message in A/B testing mode."""
        try:
            # Use existing A/B testing service
            ab_test, response_a, response_b = ABTestingService.create_ab_test_responses(
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                original_prompt=message_text,
                conversation=conversation
            )
            
            # Create Slack message format for both responses
            message_a = ABTestingService.create_slack_message_with_buttons(
                response_text=response_a.response_text,
                variant="A",
                test_id=ab_test.id,
                user_id=user_id
            )
            
            message_b = ABTestingService.create_slack_message_with_buttons(
                response_text=response_b.response_text,
                variant="B",
                test_id=ab_test.id,
                user_id=user_id
            )
            
            if not response_a or not response_b:
                return None
            
            return {
                "mode": "ab_testing",
                "responses": [
                    {
                        "text": response_a.response_text,
                        "type": "ab_response_a",
                        "slack_message": message_a,
                        "response_id": response_a.id
                    },
                    {
                        "text": response_b.response_text,
                        "type": "ab_response_b", 
                        "slack_message": message_b,
                        "response_id": response_b.id
                    }
                ],
                "metadata": {
                    "ab_test_id": ab_test.id,
                    "intro_message": f"Here are two different responses to your question. Please vote for the one you prefer!"
                }
            }
            
        except Exception as e:
            logger.error(f"Error in A/B testing mode for user {user_id}: {e}")
            raise e
    
    @staticmethod
    def switch_to_persona(user_id: str, persona_id: int) -> bool:
        """Switch user to chat mode and set active persona."""
        try:
            # Set chat mode
            if not ChatService.set_user_mode(user_id, "chat_mode"):
                return False
            
            # Set active persona
            if not PersonaManager.set_active_persona(user_id, persona_id):
                return False
            
            logger.info(f"Switched user {user_id} to chat mode with persona {persona_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error switching to persona for user {user_id}: {e}")
            return False 
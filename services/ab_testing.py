import os
import json
from typing import List, Dict, Tuple
from models import db, ABTest, ABResponse
from services.anthropic import claude, opus, sonnet
from services.user_preferences import UserPreferencesService
from utils import setup_logger

logger = setup_logger(__name__)


class ABTestingService:
    """Service for managing A/B testing of Claude responses."""
    
    @staticmethod
    def create_ab_test_responses(
        user_id: str,
        channel_id: str, 
        thread_ts: str,
        original_prompt: str,
        conversation: List[Dict]
    ) -> Tuple[ABTest, ABResponse, ABResponse]:
        """
        Create A/B test with two different response variants using user preferences.
        
        Returns:
            Tuple of (ABTest, Response A, Response B)
        """
        
        # Get user preferences
        user_prefs = UserPreferencesService.get_user_preferences(user_id)
        
        # Create AB test record
        ab_test = ABTest(
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            original_prompt=original_prompt,
            conversation_context=conversation
        )
        db.session.add(ab_test)
        db.session.flush()  # Get the ID without committing
        
        # Configuration for Response A (using user preferences)
        response_a_config = user_prefs['response_a']
        response_a_text = ABTestingService._generate_claude_response(
            conversation=conversation,
            model=response_a_config['model'],
            system_prompt=response_a_config['system_prompt'],
            temperature=response_a_config['temperature'],
            max_tokens=2000
        )
        
        response_a = ABResponse(
            test_id=ab_test.id,
            response_variant='A',
            response_text=response_a_text,
            model_name=response_a_config['model'],
            system_prompt=response_a_config['system_prompt'][:1000],  # Truncate for storage
            temperature=response_a_config['temperature'],
            max_tokens=2000
        )
        
        # Configuration for Response B (using user preferences)
        response_b_config = user_prefs['response_b']
        response_b_text = ABTestingService._generate_claude_response(
            conversation=conversation,
            model=response_b_config['model'],
            system_prompt=response_b_config['system_prompt'],
            temperature=response_b_config['temperature'],
            max_tokens=2000
        )
        
        response_b = ABResponse(
            test_id=ab_test.id,
            response_variant='B',
            response_text=response_b_text,
            model_name=response_b_config['model'],
            system_prompt=response_b_config['system_prompt'][:1000],  # Truncate for storage
            temperature=response_b_config['temperature'],
            max_tokens=2000
        )
        
        db.session.add(response_a)
        db.session.add(response_b)
        db.session.commit()
        
        logger.info(f"Created A/B test {ab_test.id} with user preferences for user {user_id}")
        
        return ab_test, response_a, response_b
    
    @staticmethod
    def _generate_claude_response(
        conversation: List[Dict],
        model: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Generate a Claude response with specific parameters."""
        try:
            # Map model names to actual model strings
            model_mapping = {
                'opus': opus,
                'sonnet': sonnet
            }
            
            actual_model = model_mapping.get(model, sonnet)  # Default to sonnet
            
            claude_message = claude.messages.create(
                model=actual_model,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=conversation,
            )
            
            # Handle potential multiple content blocks
            response = []
            for content in claude_message.content:
                if content.type == "text":
                    response.append(content.text)
            
            return "\n".join(response)
            
        except Exception as e:
            logger.error(f"Error generating Claude response: {e}")
            return f"Sorry, I encountered an error generating this response: {str(e)}"
    
    @staticmethod
    def create_slack_message_with_buttons(
        response_text: str,
        variant: str,
        test_id: int,
        user_id: str
    ) -> Dict:
        """Create Slack message block with voting button."""
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"**Response {variant}:**\n{response_text}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": f"👍 I like this one better",
                                "emoji": True
                            },
                            "action_id": f"vote_{variant.lower()}",
                            "value": json.dumps({
                                "test_id": test_id,
                                "variant": variant,
                                "voter_user_id": user_id
                            }),
                            "style": "primary"
                        }
                    ]
                },
                {
                    "type": "divider"
                }
            ]
        } 
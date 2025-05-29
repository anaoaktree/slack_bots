import os
import json
from typing import List, Dict, Tuple
from models import db, ABTest, ABResponse
from services.anthropic import get_standard_claude_response
from services.user_preferences import UserPreferencesService
from utils import setup_logger

logger = setup_logger(__name__)


class ABTestingService:
    """Service for managing A/B testing of Claude responses using personas."""
    
    @staticmethod
    def create_ab_test_responses(
        user_id: str,
        channel_id: str, 
        thread_ts: str,
        original_prompt: str,
        conversation: List[Dict]
    ) -> Tuple[ABTest, ABResponse, ABResponse]:
        """
        Create A/B test with two different persona responses.
        
        Returns:
            Tuple of (ABTest, Response A, Response B)
        """
        
        # Get user preferences (which now contain persona configurations)
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
        
        # Configuration for Response A (using selected persona)
        response_a_config = user_prefs['response_a']
        response_a_text = get_standard_claude_response(
            conversation=conversation,
            system_prompt=response_a_config['system_prompt'],
            model_name=response_a_config['model'],
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
        
        # Configuration for Response B (using selected persona)
        response_b_config = user_prefs['response_b']
        response_b_text = get_standard_claude_response(
            conversation=conversation,
            system_prompt=response_b_config['system_prompt'],
            model_name=response_b_config['model'],
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
        
        logger.info(f"Created A/B test {ab_test.id} using personas: A='{response_a_config['persona_name']}', B='{response_b_config['persona_name']}' for user {user_id}")
        
        return ab_test, response_a, response_b
    
    @staticmethod
    def create_slack_message_with_buttons(
        response_text: str,
        variant: str,
        test_id: int,
        user_id: str,
        persona_name: str = None
    ) -> Dict:
        """Create Slack message block with voting button and persona info."""
        # Get persona name for the header
        user_prefs = UserPreferencesService.get_user_preferences(user_id)
        if variant == 'A':
            persona_name = user_prefs['response_a']['persona_name']
        else:
            persona_name = user_prefs['response_b']['persona_name']
            
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"**Response {variant} ({persona_name}):**\n{response_text}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": f"👍 I prefer {persona_name}",
                                "emoji": True
                            },
                            "action_id": f"vote_{variant.lower()}",
                            "value": json.dumps({
                                "test_id": test_id,
                                "variant": variant,
                                "voter_user_id": user_id,
                                "persona_name": persona_name
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
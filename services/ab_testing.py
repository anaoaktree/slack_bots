import os
import json
from typing import List, Dict, Tuple
from models import db, ABTest, ABResponse
from services.anthropic import claude, opus, sonnet
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
        Create A/B test with two different response variants.
        
        Returns:
            Tuple of (ABTest, Response A, Response B)
        """
        
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
        
        # Configuration for Response A (Standard Assistant with Sonnet 4)
        system_prompt_a = open("prompts/assistant_prompt.txt", "r").read()
        response_a_text = ABTestingService._generate_claude_response(
            conversation=conversation,
            model=sonnet,
            system_prompt=system_prompt_a,
            temperature=0.3,
            max_tokens=2000
        )
        
        response_a = ABResponse(
            test_id=ab_test.id,
            response_variant='A',
            response_text=response_a_text,
            model_name=sonnet,
            system_prompt=system_prompt_a,
            temperature=0.3,
            max_tokens=2000
        )
        
        # Configuration for Response B (Creative Mode with Opus 4)
        system_prompt_b = open("prompts/gp-creative.txt", "r").read()
        response_b_text = ABTestingService._generate_claude_response(
            conversation=conversation,
            model=opus,
            system_prompt=system_prompt_b,
            temperature=1.0,
            max_tokens=2000
        )
        
        response_b = ABResponse(
            test_id=ab_test.id,
            response_variant='B',
            response_text=response_b_text,
            model_name=opus,
            system_prompt=system_prompt_b,
            temperature=1.0,
            max_tokens=2000
        )
        
        db.session.add(response_a)
        db.session.add(response_b)
        db.session.commit()
        
        logger.info(f"Created A/B test {ab_test.id} with responses for user {user_id}")
        
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
            claude_message = claude.messages.create(
                model=model,
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
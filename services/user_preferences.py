import os
from typing import Dict, Optional
from models import db, UserPreferences, AIPersona
from services.persona_manager import PersonaManager
from utils import setup_logger

logger = setup_logger(__name__)


class UserPreferencesService:
    """Service for managing user preferences for A/B testing and personas."""
    
    @staticmethod
    def get_user_preferences(user_id: str) -> Dict:
        """
        Get user preferences with persona-based A/B testing configuration.
        Returns personas for Response A and Response B, creating defaults if needed.
        """
        user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
        
        if not user_prefs:
            # Create user preferences with default personas
            user_prefs = UserPreferencesService._create_default_user_preferences(user_id)
        
        # Get personas for A/B testing
        persona_a = UserPreferencesService._get_ab_persona(user_id, user_prefs.ab_testing_persona_a_id, 'A')
        persona_b = UserPreferencesService._get_ab_persona(user_id, user_prefs.ab_testing_persona_b_id, 'B')
        
        return {
            'user_id': user_id,
            'response_a': {
                'persona_id': persona_a['id'],
                'persona_name': persona_a['name'],
                'model': persona_a['model'],
                'temperature': persona_a['temperature'], 
                'system_prompt': persona_a['system_prompt']
            },
            'response_b': {
                'persona_id': persona_b['id'],
                'persona_name': persona_b['name'],
                'model': persona_b['model'],
                'temperature': persona_b['temperature'],
                'system_prompt': persona_b['system_prompt']
            },
            'chat_mode_enabled': user_prefs.chat_mode_enabled,
            'active_persona_id': user_prefs.active_persona_id
        }
    
    @staticmethod
    def set_ab_testing_personas(user_id: str, persona_a_id: int, persona_b_id: int) -> bool:
        """Set the personas to use for A/B testing."""
        try:
            # Verify both personas belong to the user
            persona_a = AIPersona.query.filter_by(id=persona_a_id, user_id=user_id).first()
            persona_b = AIPersona.query.filter_by(id=persona_b_id, user_id=user_id).first()
            
            if not persona_a or not persona_b:
                logger.error(f"Invalid persona IDs for user {user_id}: A={persona_a_id}, B={persona_b_id}")
                return False
            
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            if not user_prefs:
                user_prefs = UserPreferences(user_id=user_id)
                db.session.add(user_prefs)
            
            user_prefs.ab_testing_persona_a_id = persona_a_id
            user_prefs.ab_testing_persona_b_id = persona_b_id
            db.session.commit()
            
            logger.info(f"Set A/B testing personas for user {user_id}: A={persona_a_id}, B={persona_b_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting A/B testing personas for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def update_ab_persona(user_id: str, response_key: str, persona_id: int) -> bool:
        """Update a single A/B testing persona (either response_a or response_b)."""
        try:
            # Verify persona belongs to the user
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if not persona:
                logger.error(f"Invalid persona ID {persona_id} for user {user_id}")
                return False
            
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            if not user_prefs:
                user_prefs = UserPreferences(user_id=user_id)
                db.session.add(user_prefs)
            
            if response_key == "response_a":
                user_prefs.ab_testing_persona_a_id = persona_id
            elif response_key == "response_b":
                user_prefs.ab_testing_persona_b_id = persona_id
            else:
                logger.error(f"Invalid response key: {response_key}")
                return False
            
            db.session.commit()
            
            logger.info(f"Updated {response_key} persona to {persona_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating {response_key} persona for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _get_ab_persona(user_id: str, persona_id: Optional[int], variant: str) -> Dict:
        """Get persona for A/B testing, creating default if needed."""
        if persona_id:
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if persona:
                return PersonaManager._persona_to_dict(persona)
        
        # Create or get default personas for A/B testing
        PersonaManager._ensure_default_personas(user_id)
        personas = PersonaManager.get_user_personas(user_id)
        
        if variant == 'A':
            # Use "Assistant" persona as default for Response A
            default_persona = next((p for p in personas if p['name'] == 'Assistant'), personas[0])
        else:
            # Use "Creative" persona as default for Response B  
            default_persona = next((p for p in personas if p['name'] == 'Creative'), 
                                 personas[1] if len(personas) > 1 else personas[0])
        
        return default_persona
    
    @staticmethod
    def _create_default_user_preferences(user_id: str) -> UserPreferences:
        """Create default user preferences with A/B testing personas."""
        try:
            # Ensure default personas exist
            PersonaManager._ensure_default_personas(user_id)
            personas = PersonaManager.get_user_personas(user_id)
            
            # Find default personas for A/B testing
            assistant_persona = next((p for p in personas if p['name'] == 'Assistant'), personas[0])
            creative_persona = next((p for p in personas if p['name'] == 'Creative'), 
                                  personas[1] if len(personas) > 1 else personas[0])
            
            user_prefs = UserPreferences(
                user_id=user_id,
                ab_testing_persona_a_id=assistant_persona['id'],
                ab_testing_persona_b_id=creative_persona['id'],
                chat_mode_enabled=True,  # Default to chat mode
                active_persona_id=assistant_persona['id']
            )
            
            db.session.add(user_prefs)
            db.session.commit()
            
            logger.info(f"Created default user preferences for {user_id}")
            return user_prefs
            
        except Exception as e:
            logger.error(f"Error creating default user preferences for {user_id}: {e}")
            db.session.rollback()
            raise e 
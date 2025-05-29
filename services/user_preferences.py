import os
from typing import Dict, Any, Optional
from models import db, UserPreferences
from utils import setup_logger

logger = setup_logger(__name__)


class UserPreferencesService:
    """Service for managing user-specific A/B testing preferences."""
    
    # Default settings
    DEFAULT_SETTINGS = {
        'response_a': {
            'system_prompt': 'assistant_prompt.txt',  # File reference
            'model': 'sonnet',
            'temperature': 0.3
        },
        'response_b': {
            'system_prompt': 'gp-creative.txt',  # File reference  
            'model': 'opus',
            'temperature': 1.0
        }
    }
    
    @staticmethod
    def get_user_preferences(user_id: str) -> Dict[str, Any]:
        """
        Get user preferences, creating defaults if none exist.
        
        Returns:
            Dict with 'response_a' and 'response_b' configurations
        """
        try:
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            
            if not user_prefs:
                # Create default preferences
                user_prefs = UserPreferencesService._create_default_preferences(user_id)
            
            # Load system prompts from files or use stored text
            response_a_prompt = UserPreferencesService._load_prompt(
                user_prefs.response_a_system_prompt
            )
            response_b_prompt = UserPreferencesService._load_prompt(
                user_prefs.response_b_system_prompt
            )
            
            return {
                'response_a': {
                    'system_prompt': response_a_prompt,
                    'model': user_prefs.response_a_model,
                    'temperature': user_prefs.response_a_temperature
                },
                'response_b': {
                    'system_prompt': response_b_prompt,
                    'model': user_prefs.response_b_model,
                    'temperature': user_prefs.response_b_temperature
                }
            }
            
        except Exception as e:
            logger.warning(f"Database error getting user preferences for {user_id}: {e}")
            logger.info("Falling back to default settings")
            # Return defaults on error (e.g., table doesn't exist yet)
            return UserPreferencesService._get_default_settings_dict()
    
    @staticmethod
    def update_user_preferences(
        user_id: str, 
        response_a_config: Optional[Dict[str, Any]] = None,
        response_b_config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update user preferences.
        
        Args:
            user_id: Slack user ID
            response_a_config: Dict with 'system_prompt', 'model', 'temperature'
            response_b_config: Dict with 'system_prompt', 'model', 'temperature'
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            
            if not user_prefs:
                user_prefs = UserPreferencesService._create_default_preferences(user_id)
            
            # Update Response A settings
            if response_a_config:
                if 'system_prompt' in response_a_config:
                    user_prefs.response_a_system_prompt = response_a_config['system_prompt']
                if 'model' in response_a_config:
                    user_prefs.response_a_model = response_a_config['model']
                if 'temperature' in response_a_config:
                    user_prefs.response_a_temperature = float(response_a_config['temperature'])
            
            # Update Response B settings
            if response_b_config:
                if 'system_prompt' in response_b_config:
                    user_prefs.response_b_system_prompt = response_b_config['system_prompt']
                if 'model' in response_b_config:
                    user_prefs.response_b_model = response_b_config['model']
                if 'temperature' in response_b_config:
                    user_prefs.response_b_temperature = float(response_b_config['temperature'])
            
            db.session.commit()
            logger.info(f"Updated preferences for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating user preferences for {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _create_default_preferences(user_id: str) -> UserPreferences:
        """Create default preferences for a new user."""
        defaults = UserPreferencesService.DEFAULT_SETTINGS
        
        user_prefs = UserPreferences(
            user_id=user_id,
            response_a_system_prompt=defaults['response_a']['system_prompt'],
            response_a_model=defaults['response_a']['model'],
            response_a_temperature=defaults['response_a']['temperature'],
            response_b_system_prompt=defaults['response_b']['system_prompt'], 
            response_b_model=defaults['response_b']['model'],
            response_b_temperature=defaults['response_b']['temperature']
        )
        
        db.session.add(user_prefs)
        db.session.commit()
        
        logger.info(f"Created default preferences for user {user_id}")
        return user_prefs
    
    @staticmethod
    def _load_prompt(prompt_reference: str) -> str:
        """Load prompt from file or return as-is if it's custom text."""
        try:
            # If it looks like a filename, load from prompts directory
            if prompt_reference.endswith('.txt'):
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                prompt_path = os.path.join(current_dir, "prompts", prompt_reference)
                
                if os.path.exists(prompt_path):
                    with open(prompt_path, "r") as file:
                        return file.read()
                else:
                    logger.warning(f"Prompt file not found: {prompt_path}")
                    return prompt_reference
            
            # Otherwise, treat as custom prompt text
            return prompt_reference
            
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_reference}: {e}")
            return "You are a helpful AI assistant."  # Fallback prompt
    
    @staticmethod
    def _get_default_settings_dict() -> Dict[str, Any]:
        """Get default settings as a dictionary with loaded prompts."""
        defaults = UserPreferencesService.DEFAULT_SETTINGS
        
        return {
            'response_a': {
                'system_prompt': UserPreferencesService._load_prompt(
                    defaults['response_a']['system_prompt']
                ),
                'model': defaults['response_a']['model'],
                'temperature': defaults['response_a']['temperature']
            },
            'response_b': {
                'system_prompt': UserPreferencesService._load_prompt(
                    defaults['response_b']['system_prompt']
                ),
                'model': defaults['response_b']['model'],
                'temperature': defaults['response_b']['temperature']
            }
        }
    
    @staticmethod
    def get_available_models() -> list:
        """Get list of available models."""
        return ['sonnet', 'opus']
    
    @staticmethod
    def reset_to_defaults(user_id: str) -> bool:
        """Reset user preferences to defaults."""
        try:
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            
            if user_prefs:
                db.session.delete(user_prefs)
                db.session.commit()
                logger.info(f"Reset preferences to defaults for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error resetting preferences for {user_id}: {e}")
            db.session.rollback()
            return False 
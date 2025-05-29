import os
from typing import Dict, List, Optional, Tuple
from models import db, AIPersona, UserPreferences, SystemPrompt
from services.system_prompt_manager import SystemPromptManager
from utils import setup_logger

logger = setup_logger(__name__)


class PersonaManager:
    """Service for managing AI personas with system prompt references."""
    
    # Cache to prevent repeated database setup operations
    _setup_cache = {
        'system_prompts_ensured': False,
        'user_personas_ensured': set()
    }
    
    # Default personas using system prompt titles
    DEFAULT_PERSONAS = [
        {
            'name': 'Assistant',
            'description': 'Helpful, accurate, and balanced responses for general assistance',
            'model': 'sonnet',
            'temperature': 0.3,
            'system_prompt_title': 'Assistant'
        },
        {
            'name': 'Creative',
            'description': 'Expressive, imaginative responses for creative tasks',
            'model': 'opus',
            'temperature': 1.0,
            'system_prompt_title': 'Creative Writer'
        },
        {
            'name': 'Analyst',
            'description': 'Logical, precise responses for analytical tasks',
            'model': 'sonnet',
            'temperature': 0.1,
            'system_prompt_title': 'Technical Analyst'
        }
    ]
    
    @staticmethod
    def get_user_personas(user_id: str) -> List[Dict]:
        """Get all personas for a user, creating defaults if none exist."""
        try:
            # Ensure default prompts and personas exist (with caching)
            PersonaManager._ensure_default_personas(user_id)
            
            personas = AIPersona.query.filter_by(user_id=user_id).order_by(
                AIPersona.is_favorite.desc(),
                AIPersona.usage_count.desc(),
                AIPersona.name
            ).all()
            
            return [PersonaManager._persona_to_dict(persona) for persona in personas]
            
        except Exception as e:
            logger.error(f"Error getting user personas for {user_id}: {e}")
            return PersonaManager._get_fallback_personas()
    
    @staticmethod
    def get_persona_by_id(persona_id: int, user_id: str) -> Optional[Dict]:
        """Get a specific persona by ID."""
        try:
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if persona:
                return PersonaManager._persona_to_dict(persona)
            return None
            
        except Exception as e:
            logger.error(f"Error getting persona {persona_id} for user {user_id}: {e}")
            return None
    
    @staticmethod
    def create_persona(user_id: str, name: str, model: str, temperature: float,
                      system_prompt_id: int, description: str = None) -> Optional[Dict]:
        """Create a new persona using an existing system prompt."""
        try:
            # Verify system prompt exists and user has access
            prompt = SystemPromptManager.get_prompt_by_id(system_prompt_id, user_id)
            if not prompt:
                logger.error(f"Invalid system prompt ID {system_prompt_id} for user {user_id}")
                return None
            
            # Check for duplicate name
            existing = AIPersona.query.filter_by(user_id=user_id, name=name).first()
            if existing:
                logger.error(f"Persona name '{name}' already exists for user {user_id}")
                return None
            
            persona = AIPersona(
                user_id=user_id,
                name=name,
                description=description,
                model=model,
                temperature=temperature,
                system_prompt_id=system_prompt_id,
                is_favorite=False,
                usage_count=0
            )
            
            db.session.add(persona)
            db.session.commit()
            
            logger.info(f"Created persona '{name}' for user {user_id}")
            return PersonaManager._persona_to_dict(persona)
            
        except Exception as e:
            logger.error(f"Error creating persona for user {user_id}: {e}")
            db.session.rollback()
            return None
    
    @staticmethod
    def update_persona(persona_id: int, user_id: str, name: str = None,
                      model: str = None, temperature: float = None,
                      system_prompt_id: int = None, description: str = None) -> bool:
        """Update an existing persona."""
        try:
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if not persona:
                logger.error(f"Persona {persona_id} not found for user {user_id}")
                return False
            
            if name:
                # Check for duplicate name
                existing = AIPersona.query.filter(
                    AIPersona.user_id == user_id,
                    AIPersona.name == name,
                    AIPersona.id != persona_id
                ).first()
                if existing:
                    logger.error(f"Persona name '{name}' already exists for user {user_id}")
                    return False
                persona.name = name
            
            if model:
                persona.model = model
            if temperature is not None:
                persona.temperature = temperature
            if system_prompt_id:
                # Verify system prompt exists and user has access
                prompt = SystemPromptManager.get_prompt_by_id(system_prompt_id, user_id)
                if not prompt:
                    logger.error(f"Invalid system prompt ID {system_prompt_id} for user {user_id}")
                    return False
                persona.system_prompt_id = system_prompt_id
            if description is not None:  # Allow empty string
                persona.description = description
            
            db.session.commit()
            logger.info(f"Updated persona {persona_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating persona {persona_id} for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def delete_persona(persona_id: int, user_id: str) -> bool:
        """Delete a persona (ensure user has at least one remaining)."""
        try:
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if not persona:
                logger.error(f"Persona {persona_id} not found for user {user_id}")
                return False
            
            # Ensure user will have at least one persona left
            remaining_count = AIPersona.query.filter_by(user_id=user_id).count()
            if remaining_count <= 1:
                logger.error(f"Cannot delete last persona for user {user_id}")
                return False
            
            db.session.delete(persona)
            db.session.commit()
            
            logger.info(f"Deleted persona {persona_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting persona {persona_id} for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def toggle_favorite(persona_id: int, user_id: str) -> bool:
        """Toggle favorite status for a persona."""
        try:
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if not persona:
                logger.error(f"Persona {persona_id} not found for user {user_id}")
                return False
            
            persona.is_favorite = not persona.is_favorite
            db.session.commit()
            
            logger.info(f"Toggled favorite for persona {persona_id} to {persona.is_favorite}")
            return True
            
        except Exception as e:
            logger.error(f"Error toggling favorite for persona {persona_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def increment_usage(user_id: str, persona_id: int) -> None:
        """Increment usage count for a persona and its system prompt."""
        try:
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if persona:
                persona.usage_count += 1
                # Also increment the system prompt usage
                SystemPromptManager.increment_usage(persona.system_prompt_id)
                db.session.commit()
                
        except Exception as e:
            logger.error(f"Error incrementing usage for persona {persona_id}: {e}")
            db.session.rollback()
    
    @staticmethod
    def get_active_persona(user_id: str) -> Optional[Dict]:
        """Get the active persona for chat mode."""
        try:
            from models import UserPreferences
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            
            if user_prefs and user_prefs.active_persona_id:
                return PersonaManager.get_persona_by_id(user_prefs.active_persona_id, user_id)
            
            # Default to first persona
            personas = PersonaManager.get_user_personas(user_id)
            return personas[0] if personas else None
            
        except Exception as e:
            logger.error(f"Error getting active persona for user {user_id}: {e}")
            return None
    
    @staticmethod
    def set_active_persona(user_id: str, persona_id: int) -> bool:
        """Set the active persona for chat mode."""
        try:
            from models import UserPreferences
            
            # Verify persona exists and belongs to user
            persona = AIPersona.query.filter_by(id=persona_id, user_id=user_id).first()
            if not persona:
                logger.error(f"Persona {persona_id} not found for user {user_id}")
                return False
            
            user_prefs = UserPreferences.query.filter_by(user_id=user_id).first()
            if not user_prefs:
                user_prefs = UserPreferences(user_id=user_id)
                db.session.add(user_prefs)
            
            user_prefs.active_persona_id = persona_id
            db.session.commit()
            
            logger.info(f"Set active persona to {persona_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting active persona for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def _ensure_default_personas(user_id: str) -> None:
        """Ensure default personas exist for a user - with caching to prevent repeated calls."""
        # Check if we've already ensured personas for this user
        if user_id in PersonaManager._setup_cache['user_personas_ensured']:
            return
        
        try:
            # First ensure default prompts exist (but only once)
            if not PersonaManager._setup_cache['system_prompts_ensured']:
                SystemPromptManager._ensure_default_prompts()
                PersonaManager._setup_cache['system_prompts_ensured'] = True
            
            existing_count = AIPersona.query.filter_by(user_id=user_id).count()
            if existing_count > 0:
                # Cache that this user has been set up
                PersonaManager._setup_cache['user_personas_ensured'].add(user_id)
                return  # User already has personas
            
            # Create default personas
            for persona_data in PersonaManager.DEFAULT_PERSONAS:
                # Find the system prompt by title
                prompt = SystemPrompt.query.filter_by(
                    title=persona_data['system_prompt_title'],
                    is_default=True
                ).first()
                
                if not prompt:
                    logger.error(f"Default prompt '{persona_data['system_prompt_title']}' not found")
                    continue
                
                persona = AIPersona(
                    user_id=user_id,
                    name=persona_data['name'],
                    description=persona_data['description'],
                    model=persona_data['model'],
                    temperature=persona_data['temperature'],
                    system_prompt_id=prompt.id,
                    is_favorite=(persona_data['name'] == 'Assistant'),  # Make Assistant default favorite
                    usage_count=0
                )
                db.session.add(persona)
            
            db.session.commit()
            logger.info(f"Created default personas for user {user_id}")
            
            # Cache successful setup
            PersonaManager._setup_cache['user_personas_ensured'].add(user_id)
            
        except Exception as e:
            logger.error(f"Error ensuring default personas for user {user_id}: {e}")
            db.session.rollback()
    
    @staticmethod
    def _persona_to_dict(persona: AIPersona) -> Dict:
        """Convert AIPersona model to dictionary with system prompt details."""
        system_prompt = persona.system_prompt
        return {
            'id': persona.id,
            'name': persona.name,
            'description': persona.description,
            'model': persona.model,
            'temperature': persona.temperature,
            'system_prompt': system_prompt.content,
            'system_prompt_id': system_prompt.id,
            'system_prompt_title': system_prompt.title,
            'is_favorite': persona.is_favorite,
            'usage_count': persona.usage_count,
            'created_at': persona.created_at.isoformat(),
            'updated_at': persona.updated_at.isoformat()
        }
    
    @staticmethod
    def _get_fallback_personas() -> List[Dict]:
        """Get fallback personas when database access fails."""
        return [
            {
                'id': None,
                'name': 'Assistant (fallback)',
                'description': 'Helpful, accurate, and balanced responses',
                'model': 'sonnet',
                'temperature': 0.3,
                'system_prompt': 'You are a helpful AI assistant.',
                'system_prompt_id': None,
                'system_prompt_title': 'Assistant',
                'is_favorite': True,
                'usage_count': 0,
                'created_at': '',
                'updated_at': ''
            }
        ]
    
    @staticmethod
    def _load_prompt_file(filename: str) -> str:
        """Load prompt from file."""
        try:
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            prompt_path = os.path.join(current_dir, "prompts", filename)
            
            if os.path.exists(prompt_path):
                with open(prompt_path, "r") as file:
                    return file.read()
            else:
                logger.warning(f"Prompt file not found: {prompt_path}")
                return "You are a helpful AI assistant."
                
        except Exception as e:
            logger.error(f"Error loading prompt file {filename}: {e}")
            return "You are a helpful AI assistant." 
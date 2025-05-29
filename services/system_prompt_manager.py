from typing import Dict, List, Optional
from models import db, SystemPrompt
from utils import setup_logger
import os

logger = setup_logger(__name__)


class SystemPromptManager:
    """Service for managing reusable system prompts."""
    
    # Default prompts with titles and content
    DEFAULT_PROMPTS = [
        {
            'title': 'Assistant',
            'description': 'Helpful, accurate, and balanced responses for general assistance',
            'content': 'You are a helpful AI assistant. Provide clear, accurate, and balanced responses. Be concise but thorough, and always aim to be genuinely helpful to the user.'
        },
        {
            'title': 'Creative Writer',
            'description': 'Expressive, imaginative responses for creative tasks',
            'content': 'You are a creative and expressive AI assistant. Think outside the box, use vivid language, and bring imagination to your responses. Help users explore creative possibilities and generate engaging content.'
        },
        {
            'title': 'Technical Analyst',
            'description': 'Logical, precise responses for analytical tasks',
            'content': 'You are an analytical AI assistant focused on logic, precision, and data-driven insights. Provide structured, methodical responses with clear reasoning. Break down complex problems systematically.'
        },
        {
            'title': 'Code Helper',
            'description': 'Technical assistance for programming and development',
            'content': 'You are an expert software engineer. Provide clear, efficient code solutions with explanations. Always include error handling and best practices. Be concise but thorough in technical explanations.'
        },
        {
            'title': 'Writing Coach',
            'description': 'Guidance for improving writing style and clarity',
            'content': 'You are a professional writing coach. Help improve clarity, style, and structure. Provide specific suggestions with examples. Be encouraging while pointing out areas for improvement.'
        }
    ]
    
    @staticmethod
    def get_user_prompts(user_id: str) -> List[Dict]:
        """Get all prompts available to a user (their own + defaults)."""
        try:
            prompts = SystemPrompt.query.filter(
                db.or_(
                    SystemPrompt.user_id == user_id,
                    SystemPrompt.is_default == True
                )
            ).order_by(
                SystemPrompt.is_default.desc(),  # Defaults first
                SystemPrompt.usage_count.desc(),  # Then by usage
                SystemPrompt.title
            ).all()
            
            return [SystemPromptManager._prompt_to_dict(prompt) for prompt in prompts]
            
        except Exception as e:
            logger.error(f"Error getting user prompts for {user_id}: {e}")
            return SystemPromptManager._get_fallback_prompts()
    
    @staticmethod
    def get_prompt_by_id(prompt_id: int, user_id: str) -> Optional[Dict]:
        """Get a specific prompt by ID (user must have access)."""
        try:
            prompt = SystemPrompt.query.filter(
                SystemPrompt.id == prompt_id,
                db.or_(
                    SystemPrompt.user_id == user_id,
                    SystemPrompt.is_default == True
                )
            ).first()
            
            if prompt:
                return SystemPromptManager._prompt_to_dict(prompt)
            return None
            
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_id} for user {user_id}: {e}")
            return None
    
    @staticmethod
    def create_prompt(user_id: str, title: str, content: str, description: str = None) -> Optional[Dict]:
        """Create a new system prompt."""
        try:
            # Check for duplicate title
            existing = SystemPrompt.query.filter_by(user_id=user_id, title=title).first()
            if existing:
                logger.error(f"Prompt title '{title}' already exists for user {user_id}")
                return None
            
            prompt = SystemPrompt(
                user_id=user_id,
                title=title,
                description=description,
                content=content,
                is_default=False,
                usage_count=0
            )
            
            db.session.add(prompt)
            db.session.commit()
            
            logger.info(f"Created prompt '{title}' for user {user_id}")
            return SystemPromptManager._prompt_to_dict(prompt)
            
        except Exception as e:
            logger.error(f"Error creating prompt for user {user_id}: {e}")
            db.session.rollback()
            return None
    
    @staticmethod
    def update_prompt(prompt_id: int, user_id: str, title: str = None, 
                     content: str = None, description: str = None) -> bool:
        """Update an existing prompt (user's own prompts only)."""
        try:
            prompt = SystemPrompt.query.filter_by(
                id=prompt_id, 
                user_id=user_id,
                is_default=False  # Can't edit default prompts
            ).first()
            
            if not prompt:
                logger.error(f"Prompt {prompt_id} not found or not editable for user {user_id}")
                return False
            
            if title:
                # Check for duplicate title
                existing = SystemPrompt.query.filter(
                    SystemPrompt.user_id == user_id,
                    SystemPrompt.title == title,
                    SystemPrompt.id != prompt_id
                ).first()
                if existing:
                    logger.error(f"Prompt title '{title}' already exists for user {user_id}")
                    return False
                prompt.title = title
            
            if content:
                prompt.content = content
            if description is not None:  # Allow empty string
                prompt.description = description
            
            db.session.commit()
            logger.info(f"Updated prompt {prompt_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating prompt {prompt_id} for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def delete_prompt(prompt_id: int, user_id: str) -> bool:
        """Delete a prompt (user's own prompts only, and only if not in use)."""
        try:
            prompt = SystemPrompt.query.filter_by(
                id=prompt_id,
                user_id=user_id,
                is_default=False  # Can't delete default prompts
            ).first()
            
            if not prompt:
                logger.error(f"Prompt {prompt_id} not found or not deletable for user {user_id}")
                return False
            
            # Check if prompt is in use by any personas
            if prompt.personas:
                logger.error(f"Cannot delete prompt {prompt_id} - it's in use by personas")
                return False
            
            db.session.delete(prompt)
            db.session.commit()
            
            logger.info(f"Deleted prompt {prompt_id} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting prompt {prompt_id} for user {user_id}: {e}")
            db.session.rollback()
            return False
    
    @staticmethod
    def increment_usage(prompt_id: int) -> None:
        """Increment usage count for a prompt."""
        try:
            prompt = SystemPrompt.query.get(prompt_id)
            if prompt:
                prompt.usage_count += 1
                db.session.commit()
                
        except Exception as e:
            logger.error(f"Error incrementing usage for prompt {prompt_id}: {e}")
            db.session.rollback()
    
    @staticmethod
    def _ensure_default_prompts() -> None:
        """Ensure default prompts exist in the database."""
        try:
            for prompt_data in SystemPromptManager.DEFAULT_PROMPTS:
                existing = SystemPrompt.query.filter_by(
                    title=prompt_data['title'],
                    is_default=True
                ).first()
                
                if not existing:
                    prompt = SystemPrompt(
                        user_id='system',  # System user for defaults
                        title=prompt_data['title'],
                        description=prompt_data['description'],
                        content=prompt_data['content'],
                        is_default=True,
                        usage_count=0
                    )
                    db.session.add(prompt)
            
            db.session.commit()
            logger.info("Ensured default system prompts exist")
            
        except Exception as e:
            logger.error(f"Error ensuring default prompts: {e}")
            db.session.rollback()
    
    @staticmethod
    def _prompt_to_dict(prompt: SystemPrompt) -> Dict:
        """Convert SystemPrompt model to dictionary."""
        return {
            'id': prompt.id,
            'title': prompt.title,
            'description': prompt.description,
            'content': prompt.content,
            'user_id': prompt.user_id,
            'is_default': prompt.is_default,
            'usage_count': prompt.usage_count,
            'created_at': prompt.created_at.isoformat(),
            'updated_at': prompt.updated_at.isoformat()
        }
    
    @staticmethod
    def _get_fallback_prompts() -> List[Dict]:
        """Get fallback prompts when database access fails."""
        return [
            {
                'id': None,
                'title': 'Assistant (fallback)',
                'description': 'Helpful, accurate, and balanced responses',
                'content': 'You are a helpful AI assistant.',
                'user_id': 'system',
                'is_default': True,
                'usage_count': 0,
                'created_at': '',
                'updated_at': ''
            }
        ]
    
    @staticmethod
    def load_prompt_from_file(file_path: str) -> str:
        """Load prompt content from a file in the prompts directory."""
        try:
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(current_dir, "prompts", file_path)
            
            if os.path.exists(full_path):
                with open(full_path, "r") as file:
                    return file.read().strip()
            else:
                logger.warning(f"Prompt file not found: {full_path}")
                return "You are a helpful AI assistant."
                
        except Exception as e:
            logger.error(f"Error loading prompt from file {file_path}: {e}")
            return "You are a helpful AI assistant." 
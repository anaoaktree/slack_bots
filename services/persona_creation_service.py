from typing import Dict, Optional, Tuple
from models import db
from services.persona_manager import PersonaManager
from services.system_prompt_manager import SystemPromptManager
from utils import setup_logger

logger = setup_logger(__name__)


class PersonaCreationService:
    """Service for creating personas with inline prompt management."""
    
    @staticmethod
    def create_persona_with_prompt_handling(
        user_id: str,
        persona_name: str,
        description: str,
        model: str,
        temperature: float,
        prompt_content: str,
        existing_prompt_id: Optional[int] = None,
        save_new_prompt: bool = False,
        new_prompt_title: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Create a persona with intelligent prompt handling.
        
        Returns:
            (success, message, persona_dict)
        """
        try:
            system_prompt_id = None
            
            # Case 1: Using existing prompt without modification
            if existing_prompt_id and not save_new_prompt:
                # Verify the existing prompt is accessible
                existing_prompt = SystemPromptManager.get_prompt_by_id(existing_prompt_id, user_id)
                if not existing_prompt:
                    return False, "Selected prompt not found or not accessible", None
                
                # Check if content matches existing prompt (no modification)
                if prompt_content.strip() == existing_prompt['content'].strip():
                    system_prompt_id = existing_prompt_id
                    logger.info(f"Using existing prompt {existing_prompt_id} for persona '{persona_name}'")
                else:
                    # Content was modified, treat as new prompt
                    save_new_prompt = True
                    if not new_prompt_title:
                        new_prompt_title = f"{persona_name} Prompt"
            
            # Case 2: Creating new prompt (either explicitly or due to modification)
            if save_new_prompt or not existing_prompt_id:
                if not new_prompt_title:
                    new_prompt_title = f"{persona_name} Prompt"
                
                # Create the new system prompt
                new_prompt = SystemPromptManager.create_prompt(
                    user_id=user_id,
                    title=new_prompt_title,
                    content=prompt_content,
                    description=f"Custom prompt for {persona_name} persona"
                )
                
                if not new_prompt:
                    return False, f"Failed to create system prompt '{new_prompt_title}'. Title might already exist.", None
                
                system_prompt_id = new_prompt['id']
                logger.info(f"Created new prompt '{new_prompt_title}' for persona '{persona_name}'")
            
            # Case 3: No prompt ID and not saving - error
            if not system_prompt_id:
                return False, "No system prompt specified", None
            
            # Create the persona
            persona = PersonaManager.create_persona(
                user_id=user_id,
                name=persona_name,
                model=model,
                temperature=temperature,
                system_prompt_id=system_prompt_id,
                description=description
            )
            
            if not persona:
                return False, f"Failed to create persona '{persona_name}'. Name might already exist.", None
            
            success_message = f"Successfully created persona '{persona_name}'"
            if save_new_prompt:
                success_message += f" with new prompt '{new_prompt_title}'"
            
            return True, success_message, persona
            
        except Exception as e:
            logger.error(f"Error creating persona with prompt handling: {e}")
            return False, f"Unexpected error: {str(e)}", None
    
    @staticmethod
    def get_prompt_suggestions_for_persona(persona_name: str, description: str) -> str:
        """Generate prompt suggestions based on persona name and description."""
        suggestions = {
            'code': 'You are an expert software engineer. Provide clear, efficient code solutions with explanations. Always include error handling and best practices.',
            'creative': 'You are a creative and expressive AI assistant. Think outside the box, use vivid language, and bring imagination to your responses.',
            'analyst': 'You are an analytical AI assistant focused on logic, precision, and data-driven insights. Provide structured, methodical responses.',
            'writer': 'You are a professional writing coach. Help improve clarity, style, and structure. Provide specific suggestions with examples.',
            'technical': 'You are a technical expert who explains complex concepts clearly. Break down problems systematically and provide detailed explanations.',
            'assistant': 'You are a helpful AI assistant. Provide clear, accurate, and balanced responses. Be concise but thorough.',
        }
        
        # Simple keyword matching for suggestions
        name_lower = persona_name.lower()
        desc_lower = description.lower() if description else ""
        combined = f"{name_lower} {desc_lower}"
        
        for keyword, prompt in suggestions.items():
            if keyword in combined:
                return prompt
        
        # Default suggestion
        return "You are a helpful AI assistant specialized in [your domain]. Provide clear, accurate responses with expertise in [your area]."
    
    @staticmethod
    def detect_prompt_changes(
        original_prompt_id: Optional[int],
        current_content: str,
        user_id: str
    ) -> Dict[str, bool]:
        """
        Detect if prompt content has changed and suggest actions.
        
        Returns:
            {
                'has_changes': bool,
                'suggest_save': bool,
                'is_custom': bool
            }
        """
        if not original_prompt_id:
            return {
                'has_changes': True,
                'suggest_save': True,
                'is_custom': True
            }
        
        try:
            original_prompt = SystemPromptManager.get_prompt_by_id(original_prompt_id, user_id)
            if not original_prompt:
                return {
                    'has_changes': True,
                    'suggest_save': True,
                    'is_custom': True
                }
            
            original_content = original_prompt['content'].strip()
            current_content = current_content.strip()
            
            has_changes = original_content != current_content
            is_default = original_prompt['is_default']
            
            return {
                'has_changes': has_changes,
                'suggest_save': has_changes,  # Suggest saving if there are changes
                'is_custom': not is_default
            }
            
        except Exception as e:
            logger.error(f"Error detecting prompt changes: {e}")
            return {
                'has_changes': True,
                'suggest_save': True,
                'is_custom': True
            } 
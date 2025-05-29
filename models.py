from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from typing import Optional

db = SQLAlchemy()


class ABTest(db.Model):
    """Stores A/B test configurations and metadata."""
    __tablename__ = 'ab_tests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)  # Slack user ID
    channel_id = db.Column(db.String(50), nullable=False)  # Slack channel ID
    thread_ts = db.Column(db.String(50), nullable=False)  # Slack thread timestamp
    original_prompt = db.Column(db.Text, nullable=False)  # User's original question
    conversation_context = db.Column(db.JSON, nullable=True)  # Full conversation history
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    responses = db.relationship('ABResponse', backref='test', lazy=True, cascade='all, delete-orphan')
    votes = db.relationship('ABVote', backref='test', lazy=True, cascade='all, delete-orphan')


class ABResponse(db.Model):
    """Stores the two generated responses for A/B testing."""
    __tablename__ = 'ab_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('ab_tests.id'), nullable=False)
    response_variant = db.Column(db.String(1), nullable=False)  # 'A' or 'B'
    response_text = db.Column(db.Text, nullable=False)
    
    # Model settings
    model_name = db.Column(db.String(100), nullable=False)
    system_prompt = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Float, nullable=True)
    max_tokens = db.Column(db.Integer, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Slack message details
    slack_message_ts = db.Column(db.String(50), nullable=True)  # Timestamp of the posted message


class ABVote(db.Model):
    """Stores user preferences for A/B test responses."""
    __tablename__ = 'ab_votes'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('ab_tests.id'), nullable=False)
    user_id = db.Column(db.String(50), nullable=False)  # Slack user ID of voter
    chosen_variant = db.Column(db.String(1), nullable=False)  # 'A' or 'B'
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Ensure one vote per user per test
    __table_args__ = (db.UniqueConstraint('test_id', 'user_id', name='unique_user_test_vote'),) 


class UserPreferences(db.Model):
    """Stores user-specific A/B testing preferences."""
    __tablename__ = 'user_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)  # Slack user ID
    
    # A/B Testing persona selections (reference existing personas)
    ab_testing_persona_a_id = db.Column(db.Integer, nullable=True)  # Persona ID for Response A
    ab_testing_persona_b_id = db.Column(db.Integer, nullable=True)  # Persona ID for Response B
    
    # Chat mode settings
    chat_mode_enabled = db.Column(db.Boolean, default=False)  # Whether user prefers chat mode
    active_persona_id = db.Column(db.Integer, nullable=True)  # Currently active persona for chat mode
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemPrompt(db.Model):
    """Stores reusable system prompts that can be shared across personas."""
    __tablename__ = 'system_prompts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)  # Slack user ID of creator
    title = db.Column(db.String(100), nullable=False)  # Short descriptive name
    description = db.Column(db.Text, nullable=True)  # Optional longer description
    content = db.Column(db.Text, nullable=False)  # Full prompt text
    
    # Metadata
    is_default = db.Column(db.Boolean, default=False)  # System-provided defaults
    usage_count = db.Column(db.Integer, default=0)  # Track how often it's used
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    personas = db.relationship('AIPersona', backref='system_prompt', lazy=True)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('user_id', 'title', name='unique_user_prompt_title'),
    )


class AIPersona(db.Model):
    """Stores saved AI personas that users can switch between in chat mode."""
    __tablename__ = 'ai_personas'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)  # Slack user ID
    name = db.Column(db.String(100), nullable=False)  # User-defined persona name
    description = db.Column(db.Text, nullable=True)  # Optional description
    
    # AI configuration
    model = db.Column(db.String(100), nullable=False)  # 'opus' or 'sonnet'
    temperature = db.Column(db.Float, nullable=False, default=0.7)
    system_prompt_id = db.Column(db.Integer, db.ForeignKey('system_prompts.id'), nullable=False)
    
    # Metadata
    is_favorite = db.Column(db.Boolean, default=False)  # User can mark favorites
    usage_count = db.Column(db.Integer, default=0)  # Track how often it's used
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='unique_user_persona_name'),
    ) 
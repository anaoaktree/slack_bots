from datetime import datetime, timedelta
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


class MessageProcessingJob(db.Model):
    """Track message processing jobs for PythonAnywhere async processing pattern."""
    __tablename__ = 'message_processing_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    message_key = db.Column(db.String(255), unique=True, nullable=False, index=True)  # channel:timestamp
    event_type = db.Column(db.String(50), nullable=False)  # 'message' or 'app_mention'
    user_id = db.Column(db.String(100), nullable=False)
    channel_id = db.Column(db.String(100), nullable=False)
    message_ts = db.Column(db.String(50), nullable=False)
    thread_ts = db.Column(db.String(50), nullable=True)
    message_text = db.Column(db.Text, nullable=True)
    event_payload = db.Column(db.Text, nullable=False)  # JSON serialized Slack event
    
    # Job status tracking
    status = db.Column(db.String(20), default='queued', nullable=False)  # queued, processing, completed, failed
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow(), nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Error tracking
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    
    def __repr__(self):
        return f'<MessageProcessingJob {self.message_key} status={self.status}>'
    
    @staticmethod
    def add_job(event_type, user_id, channel_id, message_ts, thread_ts, message_text, event_payload):
        """Add a new message processing job to the queue."""
        message_key = f"{channel_id}:{message_ts}"
        
        # Check if job already exists
        existing = MessageProcessingJob.query.filter_by(message_key=message_key).first()
        if existing:
            return None  # Job already exists
        
        job = MessageProcessingJob(
            message_key=message_key,
            event_type=event_type,
            user_id=user_id,
            channel_id=channel_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_text=message_text,
            event_payload=event_payload
        )
        
        try:
            db.session.add(job)
            db.session.commit()
            return job
        except Exception:
            db.session.rollback()
            return None
    
    @staticmethod
    def get_next_job():
        """Get the next job to process."""
        return MessageProcessingJob.query.filter_by(status='queued').order_by(MessageProcessingJob.created_at).first()
    
    def start_processing(self):
        """Mark job as processing."""
        self.status = 'processing'
        self.started_at = datetime.utcnow()
        db.session.commit()
    
    def complete_successfully(self):
        """Mark job as completed successfully."""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        db.session.commit()
    
    def fail_with_error(self, error_message):
        """Mark job as failed with error."""
        self.status = 'failed'
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        self.retry_count += 1
        db.session.commit()
    
    @staticmethod
    def cleanup_old_jobs(days=7):
        """Clean up completed jobs older than specified days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        old_jobs = MessageProcessingJob.query.filter(
            MessageProcessingJob.completed_at < cutoff_date,
            MessageProcessingJob.status.in_(['completed', 'failed'])
        ).all()
        
        count = len(old_jobs)
        for job in old_jobs:
            db.session.delete(job)
        
        db.session.commit()
        return count 
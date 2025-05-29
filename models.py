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
    
    # Response A settings
    response_a_system_prompt = db.Column(db.Text, nullable=True)
    response_a_model = db.Column(db.String(100), nullable=True)  # 'opus' or 'sonnet'
    response_a_temperature = db.Column(db.Float, nullable=True)
    
    # Response B settings  
    response_b_system_prompt = db.Column(db.Text, nullable=True)
    response_b_model = db.Column(db.String(100), nullable=True)  # 'opus' or 'sonnet'
    response_b_temperature = db.Column(db.Float, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 
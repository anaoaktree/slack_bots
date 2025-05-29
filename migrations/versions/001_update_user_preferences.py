"""Update user preferences table for persona-based A/B testing

Revision ID: 001_update_user_preferences
Revises: 
Create Date: 2025-05-29 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '001_update_user_preferences'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # First, let's check if the table exists and what columns it has
    # We'll use a try-catch approach to handle existing vs new tables
    
    # Check if user_preferences table exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'user_preferences' in tables:
        # Table exists, check what columns we have
        columns = [col['name'] for col in inspector.get_columns('user_preferences')]
        
        # Add new columns if they don't exist
        if 'ab_testing_persona_a_id' not in columns:
            op.add_column('user_preferences', sa.Column('ab_testing_persona_a_id', sa.Integer(), nullable=True))
        
        if 'ab_testing_persona_b_id' not in columns:
            op.add_column('user_preferences', sa.Column('ab_testing_persona_b_id', sa.Integer(), nullable=True))
        
        if 'chat_mode_enabled' not in columns:
            op.add_column('user_preferences', sa.Column('chat_mode_enabled', sa.Boolean(), default=False))
        
        if 'active_persona_id' not in columns:
            op.add_column('user_preferences', sa.Column('active_persona_id', sa.Integer(), nullable=True))
        
        # Remove old columns if they exist
        old_columns = [
            'response_a_model', 'response_a_system_prompt', 'response_a_temperature',
            'response_b_model', 'response_b_system_prompt', 'response_b_temperature'
        ]
        
        for col in old_columns:
            if col in columns:
                try:
                    op.drop_column('user_preferences', col)
                except Exception as e:
                    print(f"Could not drop column {col}: {e}")
    
    # Create system_prompts table if it doesn't exist
    if 'system_prompts' not in tables:
        op.create_table('system_prompts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.String(length=50), nullable=False),
            sa.Column('title', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('is_default', sa.Boolean(), default=False),
            sa.Column('usage_count', sa.Integer(), default=0),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'title', name='unique_user_prompt_title')
        )
    
    # Create ai_personas table if it doesn't exist
    if 'ai_personas' not in tables:
        op.create_table('ai_personas',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.String(length=50), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('model', sa.String(length=100), nullable=False),
            sa.Column('temperature', sa.Float(), nullable=False, default=0.7),
            sa.Column('system_prompt_id', sa.Integer(), nullable=False),
            sa.Column('is_favorite', sa.Boolean(), default=False),
            sa.Column('usage_count', sa.Integer(), default=0),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['system_prompt_id'], ['system_prompts.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'name', name='unique_user_persona_name')
        )


def downgrade():
    # Drop new tables
    op.drop_table('ai_personas')
    op.drop_table('system_prompts')
    
    # Add back old columns to user_preferences
    op.add_column('user_preferences', sa.Column('response_a_model', sa.String(length=100), nullable=True))
    op.add_column('user_preferences', sa.Column('response_a_system_prompt', sa.Text(), nullable=True))
    op.add_column('user_preferences', sa.Column('response_a_temperature', sa.Float(), nullable=True))
    op.add_column('user_preferences', sa.Column('response_b_model', sa.String(length=100), nullable=True))
    op.add_column('user_preferences', sa.Column('response_b_system_prompt', sa.Text(), nullable=True))
    op.add_column('user_preferences', sa.Column('response_b_temperature', sa.Float(), nullable=True))
    
    # Remove new columns
    op.drop_column('user_preferences', 'active_persona_id')
    op.drop_column('user_preferences', 'chat_mode_enabled')
    op.drop_column('user_preferences', 'ab_testing_persona_b_id')
    op.drop_column('user_preferences', 'ab_testing_persona_a_id') 
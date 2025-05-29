#!/usr/bin/env python3
"""
Test script for A/B testing functionality
"""

import os
import sys
from dotenv import load_dotenv

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server import app
from models import db, ABTest, ABResponse, ABVote
from services import ABTestingService

load_dotenv()

def test_ab_testing():
    """Test the A/B testing functionality."""
    
    with app.app_context():
        print("🧪 Testing A/B Testing Functionality\n")
        
        # Sample conversation
        sample_conversation = [
            {"role": "user", "content": "What is the capital of France?"}
        ]
        
        print("Creating A/B test...")
        try:
            # Create A/B test
            ab_test, response_a, response_b = ABTestingService.create_ab_test_responses(
                user_id="U123TEST",
                channel_id="C123TEST", 
                thread_ts="1234567890.123456",
                original_prompt="What is the capital of France?",
                conversation=sample_conversation
            )
            
            print(f"✅ A/B test created with ID: {ab_test.id}")
            print(f"✅ Response A created: {response_a.response_variant} ({response_a.model_name})")
            print(f"✅ Response B created: {response_b.response_variant} ({response_b.model_name})")
            
            # Test message creation
            print("\nTesting Slack message creation...")
            message_a = ABTestingService.create_slack_message_with_buttons(
                response_text=response_a.response_text,
                variant="A",
                test_id=ab_test.id,
                user_id="U123TEST"
            )
            
            message_b = ABTestingService.create_slack_message_with_buttons(
                response_text=response_b.response_text,
                variant="B",
                test_id=ab_test.id,
                user_id="U123TEST"
            )
            
            print("✅ Slack messages with buttons created successfully")
            
            # Test voting
            print("\nTesting voting functionality...")
            vote = ABVote(
                test_id=ab_test.id,
                user_id="U123VOTER",
                chosen_variant="A"
            )
            db.session.add(vote)
            db.session.commit()
            
            print("✅ Vote recorded successfully")
            
            # Display results
            print(f"\n📊 Test Results:")
            print(f"Test ID: {ab_test.id}")
            print(f"Original prompt: {ab_test.original_prompt}")
            print(f"Response A length: {len(response_a.response_text)} chars")
            print(f"Response B length: {len(response_b.response_text)} chars")
            print(f"Votes: {len(ab_test.votes)}")
            
            # Show first 100 chars of each response
            print(f"\nResponse A preview: {response_a.response_text[:100]}...")
            print(f"Response B preview: {response_b.response_text[:100]}...")
            
            return True
            
        except Exception as e:
            print(f"❌ Error during testing: {e}")
            import traceback
            traceback.print_exc()
            return False

def check_database_schema():
    """Check if the database tables exist and are properly configured."""
    
    with app.app_context():
        print("🔍 Checking Database Schema\n")
        
        try:
            # Check if tables exist
            inspector = db.inspect(db.engine)
            tables = inspector.get_table_names()
            
            expected_tables = ['ab_tests', 'ab_responses', 'ab_votes']
            
            for table in expected_tables:
                if table in tables:
                    print(f"✅ Table '{table}' exists")
                    columns = inspector.get_columns(table)
                    print(f"   Columns: {[col['name'] for col in columns]}")
                else:
                    print(f"❌ Table '{table}' missing")
            
            print(f"\nTotal tables in database: {len(tables)}")
            return True
            
        except Exception as e:
            print(f"❌ Error checking schema: {e}")
            return False

if __name__ == "__main__":
    print("🚀 Starting A/B Testing Validation\n")
    
    # Check schema first
    schema_ok = check_database_schema()
    
    if schema_ok:
        print("\n" + "="*50)
        # Test functionality
        test_ok = test_ab_testing()
        
        if test_ok:
            print("\n🎉 All tests passed! A/B testing is ready to use.")
        else:
            print("\n💥 Some tests failed. Check the errors above.")
    else:
        print("\n💥 Database schema issues detected. Check your models.") 
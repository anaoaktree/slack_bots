#!/usr/bin/env python3
"""
Analytics script for A/B testing results
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server import app
from models import db, ABTest, ABResponse, ABVote

load_dotenv()

def analyze_ab_tests():
    """Analyze A/B testing results and show metrics."""
    
    with app.app_context():
        print("📊 A/B Testing Analytics Dashboard\n")
        
        # Overall statistics
        total_tests = ABTest.query.count()
        total_votes = ABVote.query.count()
        
        print(f"📈 Overall Statistics:")
        print(f"   Total A/B Tests: {total_tests}")
        print(f"   Total Votes: {total_votes}")
        print(f"   Voting Rate: {(total_votes/total_tests*100) if total_tests > 0 else 0:.1f}%")
        print()
        
        # Vote distribution
        votes_a = ABVote.query.filter_by(chosen_variant='A').count()
        votes_b = ABVote.query.filter_by(chosen_variant='B').count()
        
        print(f"🗳️  Vote Distribution:")
        print(f"   Response A (Sonnet 4): {votes_a} votes ({(votes_a/total_votes*100) if total_votes > 0 else 0:.1f}%)")
        print(f"   Response B (Haiku 3.5): {votes_b} votes ({(votes_b/total_votes*100) if total_votes > 0 else 0:.1f}%)")
        print()
        
        # Recent activity (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_tests = ABTest.query.filter(ABTest.created_at >= week_ago).count()
        recent_votes = ABVote.query.filter(ABVote.voted_at >= week_ago).count()
        
        print(f"📅 Recent Activity (Last 7 Days):")
        print(f"   New Tests: {recent_tests}")
        print(f"   New Votes: {recent_votes}")
        print()
        
        # Most active users
        print(f"👥 Most Active Users (by tests):")
        user_tests = db.session.query(
            ABTest.user_id, 
            db.func.count(ABTest.id).label('count')
        ).group_by(ABTest.user_id).order_by(db.desc('count')).limit(5).all()
        
        for user_id, count in user_tests:
            print(f"   {user_id}: {count} tests")
        print()
        
        # Model performance details
        print(f"🤖 Model Performance Details:")
        
        # Get tests with votes to analyze which model wins more often
        tests_with_votes = db.session.query(ABTest).join(ABVote).all()
        
        if tests_with_votes:
            model_wins = {'A': 0, 'B': 0}
            response_lengths = {'A': [], 'B': []}
            
            for test in set(tests_with_votes):  # Remove duplicates
                # Get votes for this test
                test_votes = ABVote.query.filter_by(test_id=test.id).all()
                
                if test_votes:
                    # Count votes for each variant
                    vote_counts = {'A': 0, 'B': 0}
                    for vote in test_votes:
                        vote_counts[vote.chosen_variant] += 1
                    
                    # Winner is the variant with more votes
                    if vote_counts['A'] > vote_counts['B']:
                        model_wins['A'] += 1
                    elif vote_counts['B'] > vote_counts['A']:
                        model_wins['B'] += 1
                
                # Collect response lengths
                for response in test.responses:
                    response_lengths[response.response_variant].append(len(response.response_text))
            
            print(f"   Tests won by Response A: {model_wins['A']}")
            print(f"   Tests won by Response B: {model_wins['B']}")
            
            if response_lengths['A']:
                avg_length_a = sum(response_lengths['A']) / len(response_lengths['A'])
                print(f"   Average Response A length: {avg_length_a:.0f} chars")
            
            if response_lengths['B']:
                avg_length_b = sum(response_lengths['B']) / len(response_lengths['B'])
                print(f"   Average Response B length: {avg_length_b:.0f} chars")
        
        print()
        
        # Recent test samples
        print(f"📝 Recent Test Samples:")
        recent_tests_sample = ABTest.query.order_by(ABTest.created_at.desc()).limit(3).all()
        
        for test in recent_tests_sample:
            print(f"\n   Test ID {test.id} (User: {test.user_id}):")
            print(f"   Question: {test.original_prompt[:80]}{'...' if len(test.original_prompt) > 80 else ''}")
            print(f"   Votes: {len(test.votes)}")
            
            if test.votes:
                vote_summary = {}
                for vote in test.votes:
                    vote_summary[vote.chosen_variant] = vote_summary.get(vote.chosen_variant, 0) + 1
                print(f"   Vote breakdown: {vote_summary}")

def export_data():
    """Export A/B testing data to CSV for further analysis."""
    
    import csv
    from datetime import datetime
    
    with app.app_context():
        print("📤 Exporting A/B Testing Data...")
        
        # Export tests and responses
        filename = f"ab_test_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow([
                'test_id', 'user_id', 'channel_id', 'original_prompt', 'created_at',
                'response_variant', 'model_name', 'temperature', 'response_length',
                'votes_received', 'chosen_by_votes'
            ])
            
            # Data
            tests = ABTest.query.all()
            for test in tests:
                for response in test.responses:
                    # Count votes for this response
                    votes_for_response = ABVote.query.filter_by(
                        test_id=test.id, 
                        chosen_variant=response.response_variant
                    ).count()
                    
                    writer.writerow([
                        test.id,
                        test.user_id,
                        test.channel_id,
                        test.original_prompt,
                        test.created_at,
                        response.response_variant,
                        response.model_name,
                        response.temperature,
                        len(response.response_text),
                        votes_for_response,
                        votes_for_response > 0
                    ])
        
        print(f"✅ Data exported to {filename}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export_data()
    else:
        analyze_ab_tests()
        print("\n💡 Tip: Run 'python analytics.py export' to export data to CSV") 
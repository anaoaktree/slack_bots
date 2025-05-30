#!/usr/bin/env python3
"""
Background message processor for PythonAnywhere Always-On Task.

This script is a job orchestrator that finds jobs in the database,
calls Flask endpoints to process them, and updates job status.
Following the PythonAnywhere blog post pattern with proper separation.
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timedelta

# Add the project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('message_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database setup (independent from Flask app)
from config import config
config_name = os.environ.get('FLASK_ENV', 'development')
db_config = config[config_name]

engine = create_engine(db_config.SQLALCHEMY_DATABASE_URI, **db_config.SQLALCHEMY_ENGINE_OPTIONS)
Session = sessionmaker(bind=engine)

# Import models
from models import MessageProcessingJob

# Flask app URL for API calls
FLASK_API_BASE_URL = os.environ.get('FLASK_API_BASE_URL', 'http://127.0.0.1:5000')
if 'pythonanywhere.com' in os.environ.get('PA_DOMAIN', ''):
    # In production on PythonAnywhere, use the web app URL
    FLASK_API_BASE_URL = f"https://{os.environ.get('PA_DOMAIN', 'chachibt.pythonanywhere.com')}"

# HTTP timeout for Flask API calls
REQUEST_TIMEOUT = 30


def find_pending_job():
    """Find and mark the next pending job as processing."""
    with Session.begin() as session:
        # Find the next queued job
        queue = session.query(MessageProcessingJob).filter_by(status='queued').order_by(MessageProcessingJob.created_at)
        if job := queue.first():
            job.status = 'processing'
            job.started_at = datetime.utcnow()
            session.flush()  # Ensure the job is marked as processing
            
            # Return job details for processing
            return {
                "id": job.id,
                "message_key": job.message_key,
                "event_type": job.event_type,
                "event_payload": job.event_payload
            }
    return None


def call_flask_process_job(job):
    """Call Flask app to process the job (business logic)."""
    try:
        payload = {
            "job_id": job["id"],
            "event_payload": job["event_payload"]
        }
        
        response = requests.post(
            f"{FLASK_API_BASE_URL}/process-job",
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        
        if data["status"] == "success":
            return True, data
        else:
            logger.error(f"Flask API error processing job {job['id']}: {data}")
            return False, data
            
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error calling Flask API for job {job['id']}: {e}")
        return False, {"error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error calling Flask API for job {job['id']}: {e}")
        return False, {"error": str(e)}


def mark_job_completed(job_id):
    """Mark a job as completed."""
    with Session.begin() as session:
        session.query(MessageProcessingJob).filter_by(id=job_id).update({
            "status": "completed",
            "completed_at": datetime.utcnow()
        })


def mark_job_failed(job_id, error_message):
    """Mark a job as failed."""
    with Session.begin() as session:
        session.query(MessageProcessingJob).filter_by(id=job_id).update({
            "status": "failed",
            "completed_at": datetime.utcnow(),
            "retry_count": MessageProcessingJob.retry_count + 1,
            "error_message": error_message[:500]  # Truncate long error messages
        })


def process_single_job(job):
    """Process a single job by orchestrating the Flask API call."""
    job_id = job["id"]
    message_key = job["message_key"]
    event_type = job["event_type"]
    
    logger.info(f"⚡ ORCHESTRATING: Starting job {job_id} for {event_type} event {message_key}")
    
    try:
        # Call Flask app to do the actual processing (business logic)
        success, result = call_flask_process_job(job)
        
        if success:
            action = result.get("action", "processed")
            
            if action == "skipped":
                reason = result.get("reason", "unknown")
                logger.info(f"⏭️ SKIPPED: Job {job_id} - {reason}")
            else:
                mode = result.get("mode", "unknown")
                messages_sent = result.get("messages_sent", [])
                logger.info(f"📤 SENT: Job {job_id} - {mode} mode, {len(messages_sent)} messages sent")
            
            # Mark job as completed
            mark_job_completed(job_id)
            logger.info(f"✅ SUCCESS: Job {job_id} completed successfully")
            return True
        else:
            # Processing failed, mark job as failed
            error_message = result.get("message", "Unknown error")
            logger.error(f"❌ PROCESSING_FAILED: Job {job_id} - {error_message}")
            
            mark_job_failed(job_id, error_message)
            logger.info(f"🔴 FAILED: Job {job_id} marked as failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ EXCEPTION: Job {job_id} - unexpected error: {e}")
        import traceback
        logger.error(f"❌ TRACEBACK: Job {job_id} - {traceback.format_exc()}")
        
        # Try to mark as failed
        try:
            mark_job_failed(job_id, f"Unexpected error: {str(e)}")
        except:
            pass  # Don't fail on failure to mark as failed
        
        return False


def cleanup_old_jobs():
    """Clean up old completed jobs to prevent database bloat."""
    try:
        with Session.begin() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            old_jobs = session.query(MessageProcessingJob).filter(
                MessageProcessingJob.completed_at < cutoff_date,
                MessageProcessingJob.status.in_(['completed', 'failed'])
            ).all()
            
            count = len(old_jobs)
            for job in old_jobs:
                session.delete(job)
            
            if count > 0:
                logger.info(f"🧹 CLEANUP: Removed {count} old completed jobs")
        
    except Exception as e:
        logger.error(f"⚠️ CLEANUP_ERROR: Failed to clean up old jobs: {e}")


def test_flask_connection():
    """Test connection to Flask app."""
    try:
        response = requests.get(f"{FLASK_API_BASE_URL}/health", timeout=10)
        response.raise_for_status()
        logger.info(f"✅ Flask API connection successful to {FLASK_API_BASE_URL}")
        return True
    except Exception as e:
        logger.error(f"❌ Flask API connection failed to {FLASK_API_BASE_URL}: {e}")
        return False


def main():
    """Main job orchestration loop."""
    logger.info("🚀 JOB ORCHESTRATOR: Starting message processor job orchestrator")
    logger.info(f"📍 Working directory: {os.getcwd()}")
    logger.info(f"🌐 Flask API URL: {FLASK_API_BASE_URL}")
    
    # Test connection to Flask API
    if not test_flask_connection():
        logger.error("❌ STARTUP_FAILED: Cannot connect to Flask API. Exiting.")
        sys.exit(1)
    
    # Run cleanup on startup
    cleanup_old_jobs()
    
    jobs_processed = 0
    last_cleanup = datetime.utcnow()
    consecutive_failures = 0
    max_consecutive_failures = 10
    
    logger.info("✅ READY: Job orchestrator is ready to process jobs")
    
    while True:
        try:
            # Find and process next job
            job = find_pending_job()
            
            if job:
                success = process_single_job(job)
                if success:
                    jobs_processed += 1
                    consecutive_failures = 0  # Reset failure counter
                    logger.info(f"📊 STATS: Processed {jobs_processed} jobs total")
                else:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ WARNING: Job {job['id']} failed (consecutive failures: {consecutive_failures})")
            else:
                # No jobs found, sleep for a bit
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("🛑 SHUTDOWN: Received interrupt signal, shutting down gracefully")
            break
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"❌ MAIN_LOOP_ERROR: Unexpected error in main loop (failure #{consecutive_failures}): {e}")
            
            if consecutive_failures >= max_consecutive_failures:
                logger.error(f"❌ CRITICAL: Too many consecutive failures ({consecutive_failures}). Exiting.")
                break
            
            import traceback
            logger.error(f"❌ MAIN_LOOP_TRACEBACK: {traceback.format_exc()}")
            time.sleep(5)  # Sleep before retrying
    
    logger.info(f"✅ SHUTDOWN: Job orchestrator shut down. Total jobs processed: {jobs_processed}")


if __name__ == "__main__":
    main() 
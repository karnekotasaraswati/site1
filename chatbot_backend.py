import typing
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from rq.job import Job
from chatbot_config import REDIS_URL, APP_TITLE, APP_VERSION
import logging

# Log configurations for production-level monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(title=APP_TITLE, version=APP_VERSION)

# Initialize Redis Connection & RQ Queue
# Connect to Redis to manage the job queue
try:
    redis_conn = Redis.from_url(REDIS_URL)
    chatbot_queue = Queue("chatbot_tasks", connection=redis_conn)
    logger.info(f"Connected to Redis at {REDIS_URL}")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    # In production, you would handle this failure gracefully
    redis_conn = None
    chatbot_queue = None

# Input Validation Model
class ChatRequest(BaseModel):
    user_input: str

@app.post("/chat", summary="Push request to Redis queue")
async def chat(request: ChatRequest):
    """
    Push chat request to Redis Queue and return Job ID immediately.
    This architecture allows for handling high concurrency (10,000+ users).
    """
    if not chatbot_queue:
        raise HTTPException(status_code=500, detail="Redis is not connected. Queue unavailable.")
    
    try:
        # Import the task function locally to ensure the worker can access it properly
        from chatbot_tasks import process_chatbot_request
        
        # Enqueue the task and return job ID immediately
        # The AI model processing happens in the background by a separate worker process.
        job = chatbot_queue.enqueue(process_chatbot_request, request.user_input)
        
        logger.info(f"Chat request enqueued. Job ID: {job.get_id()}")
        
        return {
            "status": "queued",
            "job_id": job.get_id(),
            "message": "Your request has been added to the queue for processing."
        }
    except Exception as e:
        logger.error(f"Error enqueuing job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/result/{job_id}", summary="Fetch response using job ID")
async def get_result(job_id: str):
    """
    Fetch the result of a chat task using its Job ID.
    Clients poll this endpoint while the job is in 'processing' status.
    """
    if not redis_conn:
        raise HTTPException(status_code=500, detail="Redis is not connected. Data unavailable.")
    
    try:
        # Fetch the job object using its unique job ID
        job = Job.fetch(job_id, connection=redis_conn)
        
        # Return different responses based on the job status
        if job.is_queued:
            return {
                "status": "queued",
                "message": "The request is waiting in line."
            }
        elif job.is_started:
            return {
                "status": "processing",
                "message": "The AI is currently processing your request."
            }
        elif job.is_finished:
            return {
                "status": "completed",
                "result": job.result
            }
        elif job.is_failed:
            return {
                "status": "failed",
                "error": "The AI processing failed. Please try again."
            }
        else:
            return {
                "status": "unknown",
                "message": "Job status cannot be determined."
            }
    except Exception as e:
        # If the job ID is not found in Redis, the job may have expired or never existed
        logger.warning(f"Job ID result requested but not found: {job_id}")
        return {
            "status": "error",
            "message": f"Job ID '{job_id}' not found. It may have expired or is invalid."
        }

@app.get("/", summary="Root endpoint for health check")
async def root():
    """
    A simple health check endpoint to verify that the backend is up and running.
    """
    return {
        "status": "online",
        "message": f"Welcome to {APP_TITLE}",
        "version": APP_VERSION,
        "endpoints": {
            "chat": "POST /chat",
            "result": "GET /result/{job_id}"
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Use environment variables for port configuration (default 8000)
    port = int(os.getenv("PORT", 8000))
    # Run the FastAPI server in-process for development
    # In production, uvicorn is typically run via the command line
    uvicorn.run(app, host="0.0.0.0", port=port)

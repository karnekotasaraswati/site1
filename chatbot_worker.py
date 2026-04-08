import sys
import logging
from redis import Redis
from rq import Worker, Queue, Connection
from chatbot_config import REDIS_URL

# Set up logging for the worker to track job status and errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# The queue name we are watching (must match the one in our FastAPI backend)
listen = ['chatbot_tasks']

def start_worker():
    """
    Starts the Redis Queue (RQ) Worker.
    This process will listen for new jobs in 'chatbot_tasks' queue and
    execute the corresponding processing functions.
    """
    logger.info(f"Starting Redis Worker listening on: {listen}...")
    
    try:
        # Establish a connection to the Redis server
        conn = Redis.from_url(REDIS_URL)
        
        # Connect to the specified queue and begin working on jobs
        with Connection(conn):
            # Worker objects pull jobs off the queue and execute them
            # Multiple workers can be started to scale processing capacity
            worker = Worker(list(map(Queue, listen)))
            worker.work()
            
    except Exception as e:
        logger.error(f"Worker crashed with error: {e}")
        # In a real-world scenario, you would use a process manager like
        # systemd, supervisor, or PM2 to automatically restart the worker.

if __name__ == '__main__':
    # Start the worker process when the script is executed
    start_worker()

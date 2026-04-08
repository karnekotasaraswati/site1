import time
import random
import logging

# Set up logging for task progress tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_chatbot_request(user_input: str):
    """
    Simulate AI model processing with a delay of 2–5 seconds.
    This function will be called by the Redis Worker (RQ).
    """
    logger.info(f"Processing chat request: {user_input}")
    
    # Simulate processing delay (2–5 seconds)
    processing_time = random.uniform(2, 5)
    time.sleep(processing_time)
    
    # Simulate simple AI logic for a chatbot response
    responses = [
        f"Simulated response to '{user_input}': Hi! How can I help you today?",
        f"Simulated response to '{user_input}': That's an interesting question. Let me think...",
        f"Simulated response to '{user_input}': Based on my simulated knowledge, here's the answer.",
        f"Simulated response to '{user_input}': I processed your input in {processing_time:.2f} seconds."
    ]
    
    response_content = random.choice(responses)
    logger.info(f"Finished processing. Result: {response_content}")
    
    return {
        "response": response_content,
        "processing_time": round(processing_time, 2),
        "status": "success"
    }

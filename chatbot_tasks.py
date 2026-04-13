import logging
from model import llm

# Set up logging for task progress tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_chatbot_request(user_input: str):
    """
    Process chat request using the real LLM model.
    This function is called by the Redis Worker (RQ).
    The model is loaded once per worker process.
    """
    logger.info(f"Processing real AI chat request: {user_input}")
    
    try:
        # The llm.generate method handles model loading internally if not pre-warmed
        # but we also ensure it's pre-warmed in the worker startup.
        response_text = llm.generate(
            user_input, 
            max_tokens=512, 
            temperature=0.7, 
            top_p=0.9
        )
        
        return {
            "response": response_text,
            "status": "success",
            "model": "Qwen1.5-0.5B-Chat"
        }
    except Exception as e:
        logger.error(f"Error processing AI request: {e}")
        return {
            "error": str(e),
            "status": "failed"
        }

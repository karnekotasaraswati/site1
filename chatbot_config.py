import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Application Settings
APP_TITLE = "Scalable Chatbot Backend"
APP_VERSION = "1.0.0"

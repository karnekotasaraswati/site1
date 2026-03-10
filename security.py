import os
import secrets
import logging
from datetime import datetime
from fastapi import Security, HTTPException, status, Request
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv

from database import verify_api_key_pair, load_all_key_pairs

load_dotenv()

# Security Configurations
API_KEY_NAME = "X-API-Key"
API_SECRET_NAME = "X-API-Secret"
MASTER_SECRET_NAME = "X-Master-Secret"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_secret_header = APIKeyHeader(name=API_SECRET_NAME, auto_error=False)
master_secret_header = APIKeyHeader(name=MASTER_SECRET_NAME, auto_error=False)

# 🚀 In-memory cache for API Key-Secret pairs
VALID_KEY_PAIRS = {}

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("api_requests.log", encoding="utf-8")

    ]
)
logger = logging.getLogger("api_security")

def log_request(request: Request, status_code: int, api_key: str = "Anonymous"):
    """Log details of the API request."""
    client_host = request.client.host if request.client else "unknown"
    method = request.method
    url = str(request.url)
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Mask API key for logging
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "********"
    
    logger.info(f"{timestamp} | {client_host} | {method} {url} | Status: {status_code} | Key: {masked_key}")

def refresh_key_cache():
    """Refresh the global key cache from all sources."""
    global VALID_KEY_PAIRS
    try:
        VALID_KEY_PAIRS = load_all_key_pairs()
        logger.info(f"API Key Cache refreshed. Current keys: {len(VALID_KEY_PAIRS)}")
    except Exception as e:
        logger.error(f"Failed to refresh key cache: {e}")

def get_api_key(
    request: Request,
    api_key: str = Security(api_key_header),
    api_secret: str = Security(api_secret_header)
):
    if not api_key:
        log_request(request, 403, "Missing")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="API Key missing"
        )
    
    if not api_secret:
        clean_key = api_key.strip()
        # Allow pre-configured keys (like environment variables) to pass without a secret
        if clean_key in VALID_KEY_PAIRS:
            return clean_key
        else:
            logger.warning(f"Anonymous key attempt or missing secret: {clean_key}")
            log_request(request, 403, api_key)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="API Secret missing or Invalid Key"
            )




    # Clean the input keys
    clean_key = api_key.strip()
    # Handle the case where api_secret is None because it was allowed to pass above
    clean_secret = api_secret.strip() if api_secret else ""


    # Priority 1: Check in-memory cache (FASTEST)
    if clean_key in VALID_KEY_PAIRS:
        expected_secret = VALID_KEY_PAIRS[clean_key]
        # Allow if secret matches, or if no secret was provided (for known keys)
        if expected_secret is None or clean_secret == expected_secret or clean_secret == "":
            from database import update_key_usage
            update_key_usage(clean_key)
            return clean_key


    # Priority 2: Check database (fallback for newly generated keys not yet in cache)
    if verify_api_key_pair(clean_key, clean_secret):
        from database import update_key_usage
        update_key_usage(clean_key)
        # Update cache on the fly for this new key
        VALID_KEY_PAIRS[clean_key] = clean_secret
        return clean_key
    
    log_request(request, 403, clean_key)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key or Secret"
    )

def validate_master_secret(
    request: Request,
    master_secret: str = Security(master_secret_header),
):
    expected_secret = os.getenv("MASTER_SECRET")
    if not expected_secret:
        # If no master secret is set, we disable key creation via API for safety
        log_request(request, 503, "Master-Config-Error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Master authentication not configured"
        )
    
    if master_secret != expected_secret:
        log_request(request, 401, "Invalid-Master")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Master Secret"
        )
    
    return master_secret

def create_new_key(prefix: str = "sk"):
    return f"{prefix}_{secrets.token_urlsafe(32)}"

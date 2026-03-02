import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from dotenv import load_dotenv

import secrets

from database import verify_api_key

load_dotenv()

API_KEY_NAME = "X-API-Key"
MASTER_SECRET_NAME = "X-Master-Secret"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
master_secret_header = APIKeyHeader(name=MASTER_SECRET_NAME, auto_error=False)

def get_api_key(
    api_key: str = Security(api_key_header),
):
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="API Key missing"
        )

    # Priority 1: Check environment variables (comma separated)
    valid_env_keys = os.getenv("API_KEYS", "").split(",")
    valid_env_keys = [k.strip() for k in valid_env_keys if k.strip()]
    
    if api_key in valid_env_keys:
        return api_key

    # Priority 2: Check database
    if verify_api_key(api_key):
        return api_key
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key"
    )

def validate_master_secret(
    master_secret: str = Security(master_secret_header),
):
    expected_secret = os.getenv("MASTER_SECRET")
    if not expected_secret:
        # If no master secret is set, we disable key creation via API for safety
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Master authentication not configured"
        )
    
    if master_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Master Secret"
        )
    
    return master_secret

def create_new_key():
    return secrets.token_urlsafe(32)

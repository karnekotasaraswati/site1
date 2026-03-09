from dotenv import load_dotenv
load_dotenv()

import time
import os
import logging
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from security import get_api_key, validate_master_secret, create_new_key, refresh_key_cache, log_request
from model import llm
from database import init_db, save_api_key, save_chat, save_feedback

# Create a limiter that identifies users by their IP or API Key
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Starzopp AI API",
    description="Secure Backend for Stazzy - Starzopp AI Assistant",
    version="1.1.0"
)

from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# 🔒 Secure CORS Configuration
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "X-API-Secret", "X-Master-Secret", "Content-Type", "Authorization"],
)

# 🛡️ Add Trusted Host Protection
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"] if os.getenv("DEBUG") else ["site1-pf0m.onrender.com", "localhost", "127.0.0.1"]
)

# 🧱 Custom Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' unpkg.com fonts.googleapis.com; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src 'self' fonts.gstatic.com; img-src 'self' data:; connect-src 'self';"
        import uuid
        response.headers["X-Request-ID"] = str(uuid.uuid4())
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.state.limiter = limiter

# Custom handler for rate limit exceeded to log the event
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    client_ip = get_remote_address(request)
    log_request(request, 429, f"RateLimitExceeded-IP:{client_ip}")
    return await _rate_limit_exceeded_handler(request, exc)

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# 📝 Middleware for global request logging
@app.middleware("http")
async def request_logger_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # We don't want to log health checks or static files too noisily, but for security we can
    if not request.url.path.startswith(("/static", "/health", "/favicon.ico")):
        # Note: We can't easily get the API key here without re-parsing headers, 
        # so we rely on the log_request calls within dependencies for authenticated routes.
        # But we can log the general request here for unauthenticated ones.
        pass
        
    return response

# Mount the static directory
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
static_path = BASE_DIR / "static"
static_path.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.get("/")
async def read_index():
    index_file = static_path / "index.html"
    if not index_file.exists():
        # Help diagnose missing files in deployment
        logger.error(f"index.html not found at {index_file}")
        return {"detail": f"Frontend missing. Expected at {index_file}"}
    return FileResponse(str(index_file))

# --- Pydantic Models for Input Validation ---

class FeedbackRequest(BaseModel):
    prompt: str
    response: str
    feedback_type: str
    comment: Optional[str] = ""

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 256
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9

class KeyGenerationResponse(BaseModel):
    api_key: str
    api_secret: str
    description: str
    message: str

# --- API Endpoints ---

@app.on_event("startup")
async def startup_event():
    init_db()
    # 🚀 Pre-load API keys into memory cache for zero-latency lookups
    refresh_key_cache()
    print("Loading model...")
    llm.load_model()

@app.get("/verify-token")
async def verify_token(request: Request, api_key: str = Depends(get_api_key)):
    """Check if the provided API Key and Secret Key are valid."""
    log_request(request, 200, api_key)
    return {"status": "valid", "message": "Authentication successful"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "model": "TinyLlama-1.1B-Chat-v1.0"
    }

@app.get("/list-api-keys")
@limiter.limit("5/minute")
async def list_api_keys(request: Request, master_secret: str = Depends(validate_master_secret)):
    from database import get_all_keys_info
    keys = get_all_keys_info()
    log_request(request, 200, "MASTER")
    return keys

@app.delete("/revoke-api-key/{key_id}")
@app.post("/revoke-api-key/{key_id}")
@limiter.limit("5/minute")
async def revoke_api_key(request: Request, key_id: int, master_secret: str = Depends(validate_master_secret)):
    from database import delete_api_key
    if delete_api_key(key_id):
        refresh_key_cache()
        log_request(request, 200, "MASTER-REVOKE")
        return {"status": "success", "message": f"Key {key_id} revoked"}
    
    log_request(request, 500, "MASTER-REVOKE-FAIL")
    raise HTTPException(status_code=500, detail="Failed to revoke key")

@app.get("/generate-api-key", response_model=KeyGenerationResponse)
@limiter.limit("5/minute")
async def generate_api_key(
    request: Request,
    description: Optional[str] = "My Key", 
    master_secret: str = Depends(validate_master_secret)
):
    from database import save_api_key
    new_key = create_new_key(prefix="sk") # sk_... for API Key
    new_secret = create_new_key(prefix="ss") # ss_... for Secret Key

    success, error_msg = save_api_key(new_key, new_secret, description)

    if success:
        log_request(request, 201, "MASTER-GEN")
        return {
            "api_key": new_key,
            "api_secret": new_secret,
            "description": description,
            "message": "Key pair generated & stored securely"
        }

    log_request(request, 500, "MASTER-GEN-FAIL")
    raise HTTPException(status_code=500, detail=error_msg)

@app.post("/generate")
@limiter.limit("10/minute")
async def generate_response(
    request: Request,
    generate_request: GenerateRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    try:
        start_time = time.time()
        # 🚀 Move model execution to a separate thread to keep the main event loop responsive
        response = await run_in_threadpool(
            llm.generate,
            generate_request.prompt, 
            generate_request.max_tokens,
            temperature=generate_request.temperature,
            top_p=generate_request.top_p
        )
        duration = time.time() - start_time
        
        # Save to database in background
        background_tasks.add_task(save_chat, generate_request.prompt, response)
        
        log_request(request, 200, api_key)
        
        return {
            "response": response,
            "metadata": {
                "duration_seconds": round(duration, 2),
                "model": "TinyLlama-1.1B-Chat-v1.0"
            }
        }
    except Exception as e:
        log_request(request, 500, api_key)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-stream")
@limiter.limit("10/minute")
async def generate_stream(
    request: Request,
    generate_request: GenerateRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    try:
        log_request(request, 200, api_key)
        
        def stream_generator():
            full_response = []
            for chunk in llm.generate_stream(
                generate_request.prompt, 
                generate_request.max_tokens,
                temperature=generate_request.temperature,
                top_p=generate_request.top_p
            ):
                full_response.append(chunk)
                yield chunk
            
            # Save to database one finished (in background)
            background_tasks.add_task(save_chat, generate_request.prompt, "".join(full_response))

        return StreamingResponse(stream_generator(), media_type="text/plain")
    except Exception as e:
        log_request(request, 500, api_key)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
@limiter.limit("20/minute")
async def collect_feedback(
    request: Request,
    feedback: FeedbackRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    background_tasks.add_task(
        save_feedback, 
        feedback.prompt, 
        feedback.response, 
        feedback.feedback_type, 
        feedback.comment
    )
    log_request(request, 200, api_key)
    return {"status": "success", "message": "Feedback stored"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

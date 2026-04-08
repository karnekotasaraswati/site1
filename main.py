from dotenv import load_dotenv
load_dotenv()

import time
import os
import logging
logger = logging.getLogger("uvicorn.error")

from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse

from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from security import get_api_key, validate_master_secret, create_new_key, refresh_key_cache, log_request
from model import llm
from database import init_db, save_api_key, save_chat, save_feedback

import queue
import threading
import asyncio

# --- Concurrency and Queue System ---
# Global queue for LLM tasks
llm_task_queue = queue.Queue()
# Semaphore to limit concurrent processing (Initialized in startup_event)
llm_semaphore = None

def llm_worker_thread():
    """Background worker that processes LLM requests from the queue."""
    logger.info("LLM Worker Thread started.")
    while True:
        try:
            task = llm_task_queue.get()
            if task is None:
                break
            
            prompt = task['prompt']
            max_tokens = task['max_tokens']
            temperature = task['temperature']
            top_p = task['top_p']
            event = task['event']
            result_container = task['result_container']
            
            try:
                # Actual model inference call
                response = llm.generate(
                    prompt, 
                    max_tokens, 
                    temperature=temperature, 
                    top_p=top_p
                )
                result_container['response'] = response
            except Exception as e:
                logger.error(f"Error in LLM worker: {e}")
                result_container['error'] = e
            finally:
                event.set() # Signal that processing is complete
                llm_task_queue.task_done()
        except Exception as e:
            logger.error(f"LLM Worker Loop Error: {e}")

def llm_queue_gateway(prompt, max_tokens, temperature, top_p):
    """
    Interface for the endpoint to interact with the worker queue.
    This runs in a thread (via run_in_threadpool) and waits for the worker.
    """
    event = threading.Event()
    result_container = {'response': None, 'error': None}
    
    # Push work to the background queue
    llm_task_queue.put({
        'prompt': prompt,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'top_p': top_p,
        'event': event,
        'result_container': result_container
    })
    
    # Wait for the worker thread to finish processing
    event.wait()
    
    if result_container['error']:
        raise result_container['error']
    
    return result_container['response']

# Create a limiter that identifies users by their IP or API Key
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Starzopp AI API",
    description="Secure Backend for Stazzy - Starzopp AI Assistant",
    version="1.1.5" # Incremented for clear build verification
)


from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# 🔒 Secure CORS Configuration
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"], # Allow all methods for better frontend compatibility
    allow_headers=["*"], # Allow all headers including custom ones like X-API-Key
)


# Trusted Host is handled by Render's proxy, removing middleware for better compatibility



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

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    # Log the attempted path to help debug "Not Found" issues
    logger.warning(f"404 Attempted: {request.url.path}")
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return JSONResponse(
        status_code=404,
        content={
            "detail": "Path Not Found",
            "attempted_path": str(request.url.path),
            "suggestion": f"Please visit {base_url}/ to access the Stazzy assistant interface."
        }
    )


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

@app.get("/ping")
async def ping_root():
    return {"status": "online", "message": "Starzopp API is running", "path": "/ping"}


@app.get("/")
@app.get("/stazzy")
@app.get("/index.html")
@app.get("/chat")

async def read_index():
    index_file = static_path / "index.html"
    if not index_file.exists():
        logger.error(f"index.html not found at {index_file}")
        return {"detail": f"Frontend missing. Expected at {index_file}"}
    return FileResponse(str(index_file))

@app.get("/debug-files")
async def debug_files():
    import os
    try:
        root_files = os.listdir(".")
        static_files = os.listdir("./static") if os.path.exists("./static") else ["NO STATIC DIR"]
        return {
            "cwd": os.getcwd(),
            "root_files": root_files,
            "static_files": static_files,
            "base_dir": str(BASE_DIR),
            "static_path": str(static_path)
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/keys")
async def read_keys():
    return FileResponse(str(static_path / "keys.html"))

@app.get("/favicon.ico")
async def favicon():
    return FileResponse(str(static_path / "favicon.ico")) if (static_path / "favicon.ico").exists() else {"detail": "Not Found"}



# --- Pydantic Models for Input Validation ---

class FeedbackRequest(BaseModel):
    prompt: str
    response: str
    feedback_type: str
    comment: Optional[str] = ""

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 512 # Increased for complete responses
    temperature: Optional[float] = 0.5
    top_p: Optional[float] = 0.95


class KeyGenerationResponse(BaseModel):
    api_key: str
    api_secret: str
    description: str
    message: str

# --- API Endpoints ---

@app.on_event("startup")
async def startup_event():
    # Initialize the semaphore to limit concurrent LLM requests to 30
    global llm_semaphore
    llm_semaphore = asyncio.Semaphore(30)
    
    # Create background worker threads (plural) as requested
    # These will continuously pull tasks from the queue
    for i in range(30): # Matching the semaphore limit to allow 30 concurrent processes
        worker = threading.Thread(target=llm_worker_thread, daemon=True, name=f"LLMWorker-{i}")
        worker.start()

    # 🚀 Run fast setup in background
    import threading
    def background_setup():
        try:
            init_db()
            refresh_key_cache()
            print("DB/Cache Setup Complete.")
        except Exception as e:
            print(f"Setup Error: {e}")
            
    threading.Thread(target=background_setup).start()

    # 🛑 BLOCKING: Pre-load the model before accepting traffic to eliminate cold-starts
    start = time.time()
    try:
        print("Pre-warming model... Please wait.")
        llm.load_model()
        print(f"Model warmed up in {round(time.time() - start, 2)}s. Ready for traffic!")
    except Exception as e:
        print(f"CRITICAL: Failed to load model on startup! {e}")



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
        "version": "1.1.6",
        "model": "TinyLlama-1.1B"
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
        
        # 🛡️ Concurrency Control: Limit to 30 requests at a time
        # Applying semaphore inside the endpoint as requested
        async with llm_semaphore:
            # 🚀 Queue System Implementation: Instead of direct call, push to queue and wait
            # We maintain run_in_threadpool usage to keep the gateway call non-blocking for the event loop
            response = await run_in_threadpool(
                llm_queue_gateway,
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
                "model": "TinyLlama-1.1B",
                "status": "processed_via_queue"
            }
        }
    except Exception as e:
        logger.error(f"Error in /generate endpoint: {e}")
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
        
        async def stream_generator():
            full_response = []
            # 🚀 PROXY-WAKEUP: Send a tiny byte immediately to force the proxy connection open
            yield " " 
            
            import asyncio
            import threading
            
            queue = asyncio.Queue()
            
            def producer():
                try:
                    for chunk in llm.generate_stream(
                        generate_request.prompt, 
                        generate_request.max_tokens,
                        temperature=generate_request.temperature,
                        top_p=generate_request.top_p
                    ):
                        # Queue needs an event loop context.
                        # Since we are in a worker thread, we must schedule the put safely on the main loop.
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, e)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            loop = asyncio.get_running_loop()
            thread = threading.Thread(target=producer)
            thread.start()
            
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                if isinstance(chunk, Exception):
                    # For safety, let's just break, or raise
                    break
                
                full_response.append(chunk)
                yield chunk
            
            # Save to database once finished (in background)
            background_tasks.add_task(save_chat, generate_request.prompt, "".join(full_response))


        return StreamingResponse(
            stream_generator(), 
            media_type="text/plain",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

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

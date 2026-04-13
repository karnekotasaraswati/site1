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
# Global queue for LLM tasks with a max size to prevent memory bloat
llm_task_queue = queue.Queue(maxsize=100)

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
                start_exec = time.time()
                response = llm.generate(
                    prompt, 
                    max_tokens, 
                    temperature=temperature, 
                    top_p=top_p,
                    system_prompt=task.get('system_prompt')
                )
                exec_time = time.time() - start_exec
                logger.info(f"LLM Generated response in {exec_time:.2f}s")
                result_container['response'] = response
            except Exception as e:
                logger.error(f"Error in LLM worker: {e}")
                result_container['error'] = e
            finally:
                event.set() # Signal that processing is complete
                llm_task_queue.task_done()
        except Exception as e:
            logger.error(f"LLM Worker Loop Error: {e}")

def llm_queue_gateway(prompt, max_tokens, temperature, top_p, system_prompt=None):
    """
    Interface for the endpoint to interact with the worker queue.
    This runs in a thread (via run_in_threadpool) and waits for the worker.
    """
    event = threading.Event()
    result_container = {'response': None, 'error': None}
    
    # 🚀 BLOCKING FIX: Push work to the background queue with a 5s timeout
    try:
        llm_task_queue.put({
            'prompt': prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_p': top_p,
            'system_prompt': system_prompt,
            'event': event,
            'result_container': result_container
        }, timeout=5)
    except queue.Full:
        logger.error("LLM Task Queue is full.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="System is currently overloaded. Please try again later."
        )
    
    # 🚀 BLOCKING FIX: Wait for the worker thread with a 120s timeout
    if not event.wait(timeout=120):
        logger.warning(f"Worker timeout for prompt: {prompt[:50]}...")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, 
            detail="AI model processing timed out (120s limit exceeded)."
        )
    
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
    session_id: str
    question: str
    answer: str
    feedback: str  # e.g., 'up' or 'down'

class ChatRequest(BaseModel):
    session_id: Optional[str] = "default"
    question: str
    max_tokens: Optional[int] = 512 # Increased for complete responses
    temperature: Optional[float] = 0.01 # Pushed almost to 0 for 100% deterministic factual accuracy
    top_p: Optional[float] = 0.1 # Very strict sampling

class KeyGenerationResponse(BaseModel):
    api_key: str
    api_secret: str
    description: str
    message: str

# --- API Endpoints ---

@app.on_event("startup")
async def startup_event():
    # Create background worker threads (plural) as requested
    # These will continuously pull tasks from the queue
    # 🚀 OPTIMIZATION: Reduce to 2 worker threads. 
    # Multiple threads are serialized by the LLM lock anyway; 
    # fewer threads reduces context switching and memory overhead.
    for i in range(2): 
        worker = threading.Thread(target=llm_worker_thread, daemon=True, name=f"LLMWorker-{i}")
        worker.start()

    # 🚀 BLOCKING Setup: Ensure DB and API Keys are loaded before accepting traffic
    try:
        init_db()
        refresh_key_cache()
        # Initialize RAG embeddings from knowledge base
        from database import init_knowledge_base
        init_knowledge_base()
        print("DB/Cache Setup Complete.")
    except Exception as e:
        print(f"CRITICAL Setup Error: {e}")

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
        "version": "1.1.7",
        "model": "Qwen1.5-0.5B-Chat"
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

@app.get("/chat")
async def chat_info():
    return {
        "detail": "This is a POST-only AI chat endpoint.",
        "usage": "Send a POST request with 'X-API-Key' and 'X-API-Secret' headers.",
        "content_type": "application/json",
        "body_example": {"session_id": "uuid", "question": "Hello", "max_tokens": 100}
    }

@app.post("/chat")
@limiter.limit("100/minute") 
async def chat_response(
    request: Request,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    try:
        from database import retrieve_knowledge
        
        start_time = time.time()
        
        # RAG Step
        context = retrieve_knowledge(chat_request.question)
        
        # We pass context embedded in prompt or we can let llm_queue_gateway pass it
        # Actually model.py generate needs modifying to accept context
        # We will embed context directly into the prompt for the model
        SystemPrompt = (
            "You are a strict, helpful mentor. Answer in simple English. Explain step by step. "
            "CRITICAL INSTRUCTION: You MUST answer 100% accurately and ONLY use the provided 'Website Content' below. "
            "Do NOT include any external knowledge, assumptions, or hallucinations. "
            "If the answer is not explicitly contained in the Website Content, you MUST reply exactly with: 'I don't know based on the provided content.'\n\n"
            f"Website Content:\n{context}"
        )
        
        response = await run_in_threadpool(
            llm_queue_gateway,
            chat_request.question, 
            chat_request.max_tokens,
            temperature=chat_request.temperature,
            top_p=chat_request.top_p,
            system_prompt=SystemPrompt
        )
            
        duration = time.time() - start_time

        # Force strict 100% adherence: Override known LLM refusal/hallucination templates
        lower_resp = response.lower()
        refusal_flags = ["i'm sorry", "don't have access", "as an ai", "cannot provide", "vary greatly depending", "i am an ai"]
        if any(flag in lower_resp for flag in refusal_flags):
            response = "I don't know based on the provided website content."
        
        # Save to database in background
        background_tasks.add_task(save_chat, chat_request.session_id, chat_request.question, response)
        
        log_request(request, 200, api_key)
        
        return {
            "response": response,
            "metadata": {
                "duration_seconds": round(duration, 2),
                "model": "Qwen1.5-0.5B-Chat",
                "status": "processed_via_queue"
            }
        }
    except Exception as e:
        logger.error(f"Error in /chat endpoint: {e}")
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
        feedback.session_id,
        feedback.question, 
        feedback.answer, 
        feedback.feedback
    )
    log_request(request, 200, api_key)
    return {"status": "success", "message": "Feedback stored"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

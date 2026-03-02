from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import os
import time

from security import get_api_key, validate_master_secret, create_new_key
from model import llm
from database import init_db, save_api_key, save_chat

app = FastAPI(
    title="Local LLM API",
    description="FastAPI project serving TinyLlama locally",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 256
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9

class KeyResponse(BaseModel):
    api_key: str
    message: str

@app.on_event("startup")
async def startup_event():
    init_db()
    print("Loading model...")
    llm.load_model()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "model": "TinyLlama-1.1B-Chat-v1.0"
    }

@app.get("/generate-api-key", response_model=KeyResponse)
async def generate_api_key(master_secret: str = Depends(validate_master_secret)):
    new_key = create_new_key()

    success, error_msg = save_api_key(new_key)

    if success:
        return {
            "api_key": new_key,
            "message": "Key generated & stored"
        }

    raise HTTPException(status_code=500, detail=error_msg)

@app.post("/generate")
async def generate_response(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    try:
        start_time = time.time()
        response = llm.generate(
            request.prompt, 
            request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p
        )
        duration = time.time() - start_time
        
        # Save to database in background
        background_tasks.add_task(save_chat, request.prompt, response)
        
        return {
            "response": response,
            "metadata": {
                "duration_seconds": round(duration, 2),
                "model": "TinyLlama-1.1B-Chat-v1.0"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-stream")
async def generate_stream(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    try:
        def stream_generator():
            full_response = []
            for chunk in llm.generate_stream(
                request.prompt, 
                request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p
            ):
                full_response.append(chunk)
                yield chunk
            
            # Save to database one finished (in background)
            background_tasks.add_task(save_chat, request.prompt, "".join(full_response))

        return StreamingResponse(stream_generator(), media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

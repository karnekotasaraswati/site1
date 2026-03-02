# FastAPI Local LLM Server

A production-ready FastAPI project to serve a local LLM (TinyLlama) with API key authentication.

## Features
- **FastAPI** for high-performance API endpoints.
- **TinyLlama-1.1B** served via `llama-cpp-python` (GGUF).
- **API Key Authentication** for secure access.
- **Auto-download** downloads the model file if missing.
- **Health check** and **CORS** enabled.
- **Render-ready** configuration.

## Setup

1. **Clone the repository** (if applicable).
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Generate an API key**:
   ```bash
   python generate_keys.py
   ```
   This will create a `.env` file with a generated key.

4. **Run the server**:
   ```bash
   python main.py
   ```
   The model will download automatically on the first run (ensure you have ~800MB disk space).

## API Endpoints

### 1. Health Check
- **URL**: `GET /health`
- **Response**: Status information.

### 2. Generate Response
- **URL**: `POST /generate`
- **Headers**: `X-API-Key: <your_api_key>`
- **Body**:
  ```json
  {
    "prompt": "What is the capital of France?",
    "max_tokens": 128
  }
  ```

## Deployment on Render

1. Create a new **Web Service** on Render.
2. Select your repository.
3. Configure the following:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
4. Add **Environment Variables**:
   - `API_KEYS`: Your generated secret key(s).
5. **Disk Space**: Note that the model file is ~700MB. Ensure your Render plan has enough disk space or use a Persistent Disk if you don't want to download the model every time the service restarts.

## Security
- API keys are stored in the `.env` file or environment variables.
- The `generate_keys.py` utility helps manage these keys securely.

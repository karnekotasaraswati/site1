# Production-Ready Scalable Chatbot Backend

This chatbot backend uses **FastAPI** for asynchronous request handling and **Redis Queue (RQ)** to manage a scalable job processing system. 
This architecture can handle 10,000+ concurrent requests by offloading the actual "AI model" work to independent worker processes.

## Features

- **Asynchronous Chat Requests**: Pushes requests into a Redis queue and returns a Job ID immediately.
- **Job Polling**: Fetch Job status and AI response results using the Job ID.
- **Scalability**: Add more workers to handle higher traffic levels seamlessly.
- **Production-Ready**: Includes logging, configuration management, and separate task definitions.

---

## Architecture Diagram

Client → **FastAPI** (Push Request) → **Redis Queue** (Jobs) → **Worker** (AI Processing) → **Redis** (Result Storage) → **FastAPI** (Send Result to Client)

---

## 1. Installation 

### Pre-requisites
- **Python 3.8+** installed.
- **Redis Server** installed and running on your system.
  - *Windows*: Use [Redis-for-Windows](https://github.com/microsoftarchive/redis/releases) or [WSL](https://learn.microsoft.com/en-us/windows/wsl/about).
  - *Linux*: `sudo apt install redis-server`

### Install Dependencies
Run the following command to install the required Python packages:

```bash
pip install -r requirements_chatbot.txt
```

---

## 2. Configuration (`chatbot_config.py`)

Create a `.env` file or modify the defaults in `chatbot_config.py`.
- `REDIS_HOST`: Default is `localhost`.
- `REDIS_PORT`: Default is `6379`.

---

## 3. Running the Backend

Open two separate terminals:

### Terminal 1: Run the FastAPI Server
```bash
python chatbot_backend.py
```
*Your server will start on `http://localhost:8000`.*

### Terminal 2: Run the Redis Worker
```bash
python chatbot_worker.py
```
*This worker will pick up jobs from the queue and process them.*

---

## 4. API Usage Examples

### Submit a Chat Request
**POST** `http://localhost:8000/chat`
- **Body**: `{"user_input": "Hello, explain FastAPI."}`

---

### Fetch the Response
**GET** `http://localhost:8000/result/{job_id}`
- Replace `{job_id}` with the ID returned by the `/chat` endpoint.

---

## 🔒 Important Note for Windows Users
The `rq` (Redis Queue) library uses `fork()`, which is not available in Windows. To run the worker on Windows:
1. **Option A (Recommended)**: Use a Linux environment like **WSL** (Windows Subsystem for Linux).
2. **Option B**: Run the worker in a **Docker** container.
3. **Option C**: Use `rq-win` (a Windows-compatible port of RQ). Install with `pip install rq-win` and run `rq-win worker`.

---

## Scaling to 10,000+ Users
To scale this further:
1. Run multiple instances of `chatbot_worker.py` (each worker is a separate CPU core).
2. Use a production ASGI server like **Gunicorn** with **Uvicorn** workers.
3. Deploy behind a load balancer (Nginx/AWS ELB).
4. Use a managed Redis service (AWS ElastiCache/Redis Cloud) for stability.

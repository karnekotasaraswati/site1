#!/bin/bash

echo "Starting Celery worker for Windows..."
echo "Using pool=solo to prevent Windows crash bugs."

python -m celery -A celery_worker.celery_app worker --pool=solo --loglevel=info

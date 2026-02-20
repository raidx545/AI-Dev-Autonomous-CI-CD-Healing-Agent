#!/bin/bash
# Start script for Docker on Render
# Render dynamically assigns a port via the PORT environment variable.
# We must extract it and pass it to uvicorn.

PORT=${PORT:-8080}
echo "Starting backend server on port $PORT"
uvicorn app.main:app --host 0.0.0.0 --port $PORT

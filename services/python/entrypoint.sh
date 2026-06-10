#!/bin/bash
set -e

# Ensure data directory exists
mkdir -p /app/data

# Start uvicorn
exec uvicorn main:app --host 0.0.0.0 --port 8000 "$@"

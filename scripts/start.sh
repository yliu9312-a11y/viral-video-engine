#!/bin/bash
set -e

MODE=${1:-dev}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting VST services in $MODE mode..."

# Load .env if present
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
    echo "Loaded .env from $ROOT_DIR/.env"
fi

# Function to cleanup on exit
cleanup() {
    echo "Shutting down services..."
    kill $PYTHON_PID $NODE_PID $WEB_PID 2>/dev/null || true
    wait $PYTHON_PID $NODE_PID $WEB_PID 2>/dev/null || true
    echo "All services stopped."
}
trap cleanup EXIT INT TERM

# 1. Start Python FastAPI
echo "Starting Python service on :8000..."
cd "$ROOT_DIR/services/python"
PYTHONPATH="$ROOT_DIR:${PYTHONPATH:-}" uvicorn main:app --reload --port 8000 &
PYTHON_PID=$!

# 2. Start Node.js Orchestrator
echo "Starting Node orchestrator on :3000..."
cd "$ROOT_DIR/services/node"
npm run dev &
NODE_PID=$!

# 3. Start Frontend
echo "Starting frontend on :5173..."
cd "$ROOT_DIR/web"
npm run dev &
WEB_PID=$!

echo ""
echo "=========================================="
echo "VST Services Started"
echo "=========================================="
echo "Frontend:  http://localhost:5173"
echo "Node API:  http://localhost:3000"
echo "Python API:http://localhost:8000"
echo "=========================================="
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for all background processes
wait

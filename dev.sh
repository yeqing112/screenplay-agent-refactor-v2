#!/bin/bash
# DevCanvas 开发启动脚本
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Screenplay DevCanvas ==="

# Start API server
echo "[1/2] Starting API server on :18765..."
cd "$DIR"
uvicorn api.server:app --host 0.0.0.0 --port 18765 &
API_PID=$!

# Wait for API
sleep 1

# Install frontend deps if needed
if [ ! -d web/node_modules ]; then
  echo "[2/3] Installing frontend dependencies..."
  cd web && npm install && cd "$DIR"
fi

# Start frontend
echo "[3/3] Starting frontend on :5175..."
cd web && VITE_API_PROXY_TARGET=http://127.0.0.1:18765 npx vite --host 0.0.0.0 --port 5175 &
FRONTEND_PID=$!

echo ""
echo "=== DevCanvas Running ==="
echo "  API:      http://localhost:18765"
echo "  Frontend: http://localhost:5175"
echo "  Ctrl+C to stop"
echo ""

trap "kill $API_PID $FRONTEND_PID 2>/dev/null" EXIT
wait

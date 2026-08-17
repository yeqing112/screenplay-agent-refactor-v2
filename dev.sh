#!/bin/bash
# DevCanvas 开发启动脚本
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Screenplay DevCanvas ==="

# Start API server
echo "[1/2] Starting API server on :8765..."
cd "$DIR"
uvicorn api.server:app --host 0.0.0.0 --port 8765 &
API_PID=$!

# Wait for API
sleep 1

# Install frontend deps if needed
if [ ! -d web/node_modules ]; then
  echo "[2/3] Installing frontend dependencies..."
  cd web && npm install && cd "$DIR"
fi

# Start frontend
echo "[3/3] Starting frontend on :5173..."
cd web && npx vite --host 0.0.0.0 &
FRONTEND_PID=$!

echo ""
echo "=== DevCanvas Running ==="
echo "  API:      http://localhost:8765"
echo "  Frontend: http://localhost:5173"
echo "  Ctrl+C to stop"
echo ""

trap "kill $API_PID $FRONTEND_PID 2>/dev/null" EXIT
wait

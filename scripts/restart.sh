#!/bin/bash
# BuddyHelps server restart script
# Handles graceful shutdown and GPU memory cleanup

set -e

echo "=== BuddyHelps Restart Script ==="

# 1. Graceful shutdown of existing server
echo "Stopping existing server..."
pkill -TERM -f "python -m src.main" 2>/dev/null || true
sleep 3

# 2. Force kill if still running
if pgrep -f "python -m src.main" > /dev/null; then
    echo "Force killing..."
    pkill -9 -f "python -m src.main" 2>/dev/null || true
    sleep 2
fi

# 3. Clean up any orphaned vLLM processes
pkill -9 -f "vllm" 2>/dev/null || true
pkill -9 -f "EngineCore" 2>/dev/null || true
sleep 2

# 4. Clear GPU memory cache
echo "Clearing GPU memory..."
python3 -c "
import torch
import gc
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    print(f'GPU memory after cleanup: {torch.cuda.memory_allocated()/1e9:.2f}GB allocated')
" 2>/dev/null || true

# 5. Kill Jupyter if it's using port 8888
if lsof -i :8888 > /dev/null 2>&1; then
    echo "Killing process on port 8888..."
    pkill -9 jupyter 2>/dev/null || true
    sleep 1
fi

# 6. Show GPU state
echo "GPU state:"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv

# 7. Wait for GPU to stabilize
echo "Waiting for GPU to stabilize..."
sleep 3

# 8. Start server
echo "Starting server..."
source /workspace/venv/bin/activate
cd /workspace/buddyhelps-runpod
PORT=8888 nohup python -m src.main > server.log 2>&1 &

echo "Server started. PID: $!"
echo "Tail logs with: tail -f /workspace/buddyhelps-runpod/server.log"

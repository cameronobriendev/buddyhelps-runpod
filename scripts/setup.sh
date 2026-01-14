#!/bin/bash
# BuddyHelps Voice Server Setup Script
# Run this on a fresh RunPod instance

set -e

echo "=========================================="
echo "BuddyHelps Voice Server Setup"
echo "=========================================="

# System dependencies (for Kokoro TTS)
echo ""
echo "[1/5] Installing system dependencies..."
apt-get update
apt-get install -y espeak-ng ffmpeg

# CRITICAL: Pin cuda-python version
# 13.x breaks CUDA graphs = 22x slowdown (800ms instead of 34ms)
echo ""
echo "[2/5] Installing cuda-python==12.6.2 (CRITICAL VERSION)..."
pip install cuda-python==12.6.2

# PyTorch with CUDA (if not already installed)
echo ""
echo "[3/5] Checking PyTorch..."
python -c "import torch; print(f'PyTorch {torch.__version__} with CUDA {torch.version.cuda}')" || {
    echo "Installing PyTorch..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
}

# Install Python dependencies
echo ""
echo "[4/5] Installing Python dependencies..."
pip install -r requirements.txt

# Download models
echo ""
echo "[5/5] Downloading models (this may take a few minutes)..."
python -c "
import sys
sys.path.insert(0, '.')

print('Downloading Parakeet STT...')
import nemo.collections.asr as nemo_asr
stt_model = nemo_asr.models.ASRModel.from_pretrained('nvidia/parakeet-tdt-0.6b-v2')
print('  Parakeet downloaded.')

print('Downloading Kokoro TTS...')
from kokoro import KPipeline
tts_pipeline = KPipeline(lang_code='a')
print('  Kokoro downloaded.')

print('Downloading Qwen2.5-0.5B LLM...')
from vllm import LLM
llm = LLM(model='Qwen/Qwen2.5-0.5B-Instruct', dtype='float16', gpu_memory_utilization=0.3)
print('  Qwen downloaded.')

print('')
print('All models downloaded successfully!')
"

echo ""
echo "=========================================="
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run warmup: python scripts/warmup.py"
echo "  2. Start server: python -m src.main"
echo "=========================================="

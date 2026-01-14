# BuddyHelps RunPod Voice Server

Self-hosted voice AI inference for BuddyHelps. Runs on RunPod RTX A5000 Secure Cloud.

## Stack

| Component | Model | Latency | VRAM |
|-----------|-------|---------|------|
| STT | Parakeet-TDT-0.6b-v2 | 34-38ms | ~2GB |
| LLM | Qwen2.5-0.5B-Instruct | 15-30ms | ~1.2GB |
| TTS | Kokoro-82M | 105ms | ~2.5GB |
| **Total** | | **<160ms** | **~5.7GB** |

## RunPod Setup

1. Create a GPU Pod on RunPod:
   - GPU: RTX A5000 24GB (or T4 16GB minimum)
   - Template: PyTorch 2.1+ with CUDA 12.1
   - Region: US-West (lowest latency to Alberta)
   - Tier: **Secure Cloud** (99.99% SLA)

2. SSH into the pod:
   ```bash
   ssh root@[pod-ip] -i ~/.ssh/runpod_key
   ```

3. Clone and setup:
   ```bash
   git clone https://github.com/yourusername/buddyhelps-runpod.git
   cd buddyhelps-runpod
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

4. Run warmup (CRITICAL - compiles CUDA graphs):
   ```bash
   python scripts/warmup.py
   ```

5. Start the server:
   ```bash
   python -m src.main
   ```

## Critical Requirements

### cuda-python Version (DO NOT CHANGE)

```bash
# CORRECT - CUDA graphs work, 34ms latency
pip install cuda-python==12.6.2

# WRONG - 22x slowdown, 800ms latency
pip install cuda-python  # installs 13.x
```

### Warmup Required

First transcription after model load takes ~850ms (CUDA graph compilation).
Always run `scripts/warmup.py` before accepting calls.

### Quantization

Qwen2.5-0.5B loses 10-20% quality at INT4. Use FP16 only.

## API Endpoints

### Health Check
```
GET /health
```

### Speech-to-Text
```
POST /stt
Content-Type: audio/wav

[raw audio bytes]
```

### LLM Inference
```
POST /llm
Content-Type: application/json

{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "business_name": "ABC Plumbing",
  "owner_name": "Mike"
}
```

### Text-to-Speech
```
POST /tts
Content-Type: application/json

{
  "text": "Hello, this is Benny with ABC Plumbing.",
  "voice": "af_heart"
}
```

### Full Pipeline (STT -> LLM -> TTS)
```
POST /pipeline
Content-Type: audio/wav

[raw audio bytes]

Query params:
- business_id: UUID of the business
- session_id: UUID of the call session
```

## WebSocket Stream

For real-time voice processing with SignalWire:

```
WSS /ws/stream?business_id=xxx&session_id=xxx
```

Receives audio chunks, returns audio responses.

## Environment Variables

```bash
# Required
DATABASE_URL=postgresql://...
SIGNALWIRE_PROJECT_ID=...
SIGNALWIRE_TOKEN=...

# Optional
PORT=8000
LOG_LEVEL=info
VOICE=af_heart
```

## Costs

- RunPod A5000 Secure (24/7): ~$120/month
- Serves 20-40 concurrent calls
- Per-call cost: ~$0.01 (GPU amortized)

## Testing

```bash
# Test STT
curl -X POST http://localhost:8000/stt \
  -H "Content-Type: audio/wav" \
  --data-binary @test.wav

# Test TTS
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "af_heart"}' \
  --output response.wav
```

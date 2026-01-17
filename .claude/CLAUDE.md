# BuddyHelps RunPod

## What This Is

Self-hosted voice AI inference server for BuddyHelps. Runs on RunPod GPU cloud.

## Related Project

**Dashboard:** `/home/cameronobrien/Documents/GitHub/buddyhelps-dashboard`
- Admin UI, call details pages, photo upload
- Receives webhooks from this server when calls complete
- See `buddyhelps-dashboard/.claude/CLAUDE.md` for dashboard details

**Comprehensive Build Plan:** `docs/BUILD_PLAN.md`
- Single source of truth for what's built vs not built
- Covers both projects
- Recommended build order

**Architecture Diagram:** `buddyhelps-dashboard/architecture.html`

---

## Current Deployment

| Item | Value |
|------|-------|
| Pod ID | `9fal0rjnh2vqbj` |
| Pod Name | `buddyhelps` |
| GPU | RTX A4000 (16GB VRAM) |
| API URL | `https://9fal0rjnh2vqbj-8888.proxy.runpod.net` |
| SSH | `ssh root@157.157.221.29 -p 20609 -i ~/.ssh/runpod_ed25519` |
| Venv | `/workspace/venv` (persistent across restarts) |
| Cost | ~$0.19/hr (~$4.56/day) |

## Stack

| Component | Model | Latency | VRAM | Concurrency |
|-----------|-------|---------|------|-------------|
| STT | 4x faster-whisper (base) | ~150-180ms | ~2.8GB | **4 concurrent** |
| LLM | Qwen2.5-0.5B-Instruct (vLLM) | 15-30ms | ~1.2GB | 100+ (batched) |
| TTS | Kokoro-82M | ~100ms | ~2.5GB | 1 |
| **Total** | | **~280ms** | **~7.5GB** | **4 calls** |

**STT Backend Options:**
- `whisper` (default) - 4x faster-whisper instances, 4x concurrency, MIT licensed
- `parakeet` - Single NeMo instance, 64ms latency, Apache 2.0 licensed

Set via `STT_BACKEND` env var or in config.py.

## Quick Start (Resume Pod)

```bash
# 1. SSH into pod (port changes on restart - check RunPod dashboard)
ssh -o StrictHostKeyChecking=no root@157.157.221.29 -p 20609 -i ~/.ssh/runpod_ed25519

# 2. Use the restart script (handles GPU cleanup, graceful shutdown)
/workspace/buddyhelps-runpod/scripts/restart.sh

# 3. Watch logs (wait ~45s for models to load)
tail -f /workspace/buddyhelps-runpod/server.log

# 4. Test health
curl https://9fal0rjnh2vqbj-8888.proxy.runpod.net/health
```

**Manual start (if needed):**
```bash
pkill -9 jupyter  # Kill Jupyter on port 8888
source /workspace/venv/bin/activate
cd /workspace/buddyhelps-runpod
PORT=8888 nohup python -m src.main > server.log 2>&1 &
```

## Critical Gotchas

### 1. Port 8888 is Jupyter by Default
RunPod starts Jupyter on 8888. Must `pkill -9 jupyter` before starting our server.

### 2. SSH Key Must Be ED25519
RunPod SSH proxy doesn't work well with RSA keys. Use:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/runpod_ed25519
```
Add public key to RunPod account settings.

### 3. Use Direct TCP SSH, Not Proxy
Don't use `ssh.runpod.io` - use the direct IP:port from pod details.

### 4. CUDA Driver Version (12.4 vs 12.6)
RunPod's CUDA driver is 12.4. NeMo/Parakeet wants 12.6+ for CUDA graphs.
- Without graphs: STT runs at ~64ms
- With graphs: STT would run at ~34ms
- Still functional, just slightly slower

### 5. Pip Dependencies Are Fragile
vllm, NeMo, torch versions must match. Current working combo:
- torch 2.9.0
- vllm 0.13.0
- nemo_toolkit 2.6.1
- numpy 1.26.4 (NOT 2.x - breaks NeMo)

Don't randomly upgrade packages.

### 6. Root Overlay Has Limited Space (20GB)
Pip cache fills up fast. If "No space left on device":
```bash
pip cache purge
rm -rf /root/.cache/pip/*
```

### 7. Models Cache to HuggingFace
First run downloads models (~2GB). Subsequent runs use cache at `/root/.cache/huggingface/`.

### 8. Use Persistent Venv at /workspace/venv
**Root overlay (20GB) is NOT persistent.** Packages installed with `pip install` go to root overlay and are LOST on pod restart.

Solution: Use a venv at `/workspace/venv` which persists across restarts.

```bash
# Create venv (one-time)
python -m venv /workspace/venv

# Always activate before running
source /workspace/venv/bin/activate
pip install -r requirements.txt
```

### 9. SSH Port Changes on Restart
The SSH port changes every time the pod restarts. Don't hardcode it.

To get current port:
```bash
curl -sS "https://api.runpod.io/graphql" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { pod(input: {podId: \"9fal0rjnh2vqbj\"}) { runtime { ports { privatePort publicPort ip } } } }"}' | jq '.data.pod.runtime.ports'
```

### 10. Torch Version Must Be 2.3+ for NeMo
NeMo 2.6.1 requires `torch.distributed.device_mesh` which was added in PyTorch 2.3.

If you see `ModuleNotFoundError: No module named 'torch.distributed.device_mesh'`:
```bash
pip install 'torch>=2.5.0' --upgrade
```

Also requires `numpy<2` (NeMo compiled against NumPy 1.x).

### 11. vLLM GPU Memory Profiling Errors
vLLM profiles GPU memory during init. If memory changes (other processes releasing), it fails with:
```
AssertionError: Error in memory profiling. Initial free memory X GiB, current free memory Y GiB
```

**Solutions:**
- Use `scripts/restart.sh` which does proper GPU cleanup before starting
- vLLM configured with `enforce_eager=True` to disable CUDA graphs (more stable restarts)
- Never use `pkill -9` directly - use graceful shutdown (SIGTERM first)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check, model status |
| `/stt` | POST | Speech-to-text (audio bytes) |
| `/stt/stats` | GET | STT pool statistics (whisper backend) |
| `/llm` | POST | LLM inference |
| `/tts` | POST | Text-to-speech |
| `/pipeline` | POST | Full STT→Corrections→LLM→TTS pipeline |
| `/admin` | GET | Admin UI (3 tabs: Numbers, Prompts, Keywords) |
| `/api/numbers` | GET/POST/PUT/DELETE | CRUD for phone number configs |
| `/api/prompts` | GET/POST/PUT/DELETE | CRUD for system prompts |
| `/api/keywords` | GET/POST/PUT/DELETE | CRUD for keyword corrections |

## Phone Provider: Twilio

SignalWire doesn't have Alberta numbers. Using Twilio instead.
- Credentials in `.env`
- Need to buy Alberta number and wire up WebSocket handler

## RunPod API

Check pod status:
```bash
cat > /tmp/check.sh << 'SCRIPT'
#!/bin/bash
set -a && source ~/.env && set +a
curl -sS "https://api.runpod.io/graphql" \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { pod(input: {podId: \"9fal0rjnh2vqbj\"}) { id runtime { uptimeInSeconds ports { privatePort publicPort ip } } } }"}' | jq .
SCRIPT
chmod +x /tmp/check.sh && /tmp/check.sh
```

## What's NOT Here Yet

See `docs/BUILD_PLAN.md` for comprehensive list with priorities and build order.

**Summary:**
- 🔴 **Core:** Twilio WebSocket handler, audio conversion, webhook handlers
- 🟡 **Post-call:** /extract endpoint, notifications to dashboard
- 🟠 **Scale:** Pod assignment, health monitoring

## Files

- `src/stt_whisper.py` - Multi-instance faster-whisper pool (4x concurrency)
- `src/stt.py` - Parakeet STT wrapper (legacy/fallback)
- `src/stt_corrections.py` - Keyword corrections for STT output
- `src/llm.py` - Qwen LLM wrapper with vLLM
- `src/tts.py` - Kokoro TTS wrapper (handles generator API)
- `src/main.py` - FastAPI server with conditional STT loading
- `src/database.py` - SQLite database (phone numbers, prompts, keywords)
- `src/admin.py` - Admin routes + tabbed HTML UI
- `src/config.py` - Pydantic settings (STT backend selection)
- `scripts/restart.sh` - Graceful restart with GPU cleanup
- `prompts/conversation.txt` - Benny's conversation prompt
- `.env` - Credentials (Twilio, SignalWire, RunPod)
- `docs/CONCURRENCY_ANALYSIS.md` - Capacity analysis for plumber clients

## Capacity (January 2026)

With 4x faster-whisper instances:
- **40-60 solo plumbers** (vs 10-20 before)
- **15-25 small businesses** (vs 5-10 before)
- **Cost per client: $2-4/month** (vs $9-14 before)

See `docs/CONCURRENCY_ANALYSIS.md` for full analysis.

---

*Last Updated: January 16, 2026*

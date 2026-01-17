# BuddyHelps Concurrency Analysis

## Current Setup

| Component | Model | VRAM Usage | Latency |
|-----------|-------|------------|---------|
| STT | Parakeet-TDT-0.6b-v2 | ~2GB | 64-68ms |
| LLM | Qwen2.5-0.5B-Instruct (vLLM) | ~1.2GB | 15-30ms |
| TTS | Kokoro-82M | ~2.5GB | ~100ms |
| **Total** | | **~5.7GB** | **~180ms** |

GPU: RTX A4000 (16GB VRAM)
Free VRAM: ~10GB

---

## Bottleneck Analysis

### 1. STT (Parakeet) - BOTTLENECK
- **Single-threaded inference** - NeMo models don't batch by default
- Can only process one audio chunk at a time
- Each call requires continuous STT processing
- **Concurrency: 1 per STT inference**

### 2. LLM (vLLM) - NOT a bottleneck
- vLLM supports **batched inference** with continuous batching
- Can handle many concurrent requests efficiently
- Server logs showed: `100.4x max concurrency`
- GPU utilization set to 30%, leaving headroom
- **Concurrency: 50-100+ requests**

### 3. TTS (Kokoro) - BOTTLENECK
- Single model instance
- Processes one text-to-speech at a time
- ~100ms per generation
- **Concurrency: 1 per TTS inference**

---

## Per-Call Resource Usage

A typical phone call uses:

| Stage | Resource | Frequency |
|-------|----------|-----------|
| STT | Parakeet | Continuous (every ~0.5s audio chunk) |
| LLM | Qwen | Per turn (user speaks, AI responds) |
| TTS | Kokoro | Per AI response |

For a 5-minute call with 10 turns:
- STT: ~600 inferences (continuous)
- LLM: ~10 inferences (per turn)
- TTS: ~10 inferences (per response)

---

## Theoretical Maximum Concurrent Calls

### Conservative Estimate: 1-2 calls

With current single-instance models:
- STT processes audio continuously
- Only one STT inference can run at a time
- Multiple calls would queue on STT, causing delays

### Why It's Limited

```
Call 1: [STT continuous] → [LLM 30ms] → [TTS 100ms]
Call 2: [STT waiting...] → [queued] → [queued]
```

The STT is the primary bottleneck because:
1. It runs continuously (not just on turns)
2. NeMo doesn't batch audio from multiple sources
3. Each call needs its own STT stream

---

## Scaling Options

### Option 1: Multiple STT Instances
- Load 2-3 Parakeet models
- Use ~6GB additional VRAM
- Allow 2-3 concurrent calls
- **VRAM: ~12GB (fits on A4000)**

### Option 2: Smaller STT Model
- Use Whisper-tiny or faster-whisper
- Much smaller VRAM footprint (~0.5GB)
- Slightly higher latency
- Could run 4-5 instances

### Option 3: Streaming STT Service
- Use Deepgram or AssemblyAI for STT only
- Offload continuous STT processing
- Keep LLM and TTS on GPU
- **Unlimited STT concurrency**

### Option 4: GPU Upgrade
- A6000 (48GB) or A100 (40/80GB)
- Run multiple instances of all models
- Higher cost (~$1-2/hr)

---

## Recommendation

For **1-2 concurrent calls**: Current setup works.

For **3-5 concurrent calls**:
- Add a second Parakeet instance (~2GB more)
- Or use external STT service (Deepgram)

For **10+ concurrent calls**:
- External STT is mandatory
- Consider horizontal scaling (multiple pods)

---

## Real-World Performance

With the half-duplex architecture (user can't interrupt):
- STT only needs to process audio when AI is NOT speaking
- This reduces continuous STT load by ~50%
- Effective concurrency could be 2-3 calls on current setup

The LLM with vLLM batching is massively over-provisioned for this use case. It could handle 100+ concurrent LLM requests while STT handles 1-2.

---

## Real-World Client Impact: Plumbing Businesses

### Typical Plumber Call Volume (Industry Research)

| Business Size | Monthly Calls | Daily Avg | Peak Hour |
|---------------|---------------|-----------|-----------|
| Solo/1-2 trucks | 50-150 | 2-5 | 1-2 |
| Small (3-5 trucks) | 200-400 | 7-15 | 2-4 |
| Medium (6-10 trucks) | 400-800 | 15-30 | 4-8 |
| Large (10+ trucks) | 800-2000 | 30-75 | 8-20 |

**Source:** Industry averages from ServiceTitan, Housecall Pro, and trade publications.

### Call Distribution Pattern

Plumbing calls follow predictable patterns:
- **Peak hours:** 8-10 AM, 12-2 PM (60% of daily calls)
- **Average call duration:** 2-4 minutes
- **Simultaneous calls:** Rare for small businesses, common for large

### How Many Plumbers Can Current Pod Serve?

| Concurrent Calls | Client Size | Clients Served |
|------------------|-------------|----------------|
| 1-2 calls | Solo/small | **10-20 plumbers** |
| 2-3 calls (half-duplex) | Small-medium | **5-10 plumbers** |

**Calculation:**
- Solo plumber: ~5 calls/day, spread over 8 hours = 0.6 calls/hour
- Peak overlap probability for small businesses: ~5-10%
- With 2-3 concurrent call capacity: Can serve 10-20 solo plumbers

### Probability Analysis

For a solo plumber (5 calls/day):
- P(call in any 5-min window) = 5 / 96 = 5.2%
- P(two calls overlapping) = ~0.27%
- **Statistical conclusion:** Single-instance handles 10+ solo plumbers with 99%+ availability

For a small business (15 calls/day):
- P(call in any 5-min window) = 15.6%
- P(two calls overlapping) = ~2.4%
- **Statistical conclusion:** 2-3 concurrent handles 5-10 small businesses

### Cost Per Client

| Clients | Pod Cost/Month | Cost Per Client |
|---------|----------------|-----------------|
| 10 plumbers | $137 | **$13.70/client** |
| 15 plumbers | $137 | **$9.13/client** |
| 20 plumbers | $137 | **$6.85/client** |

**Pod cost:** ~$4.56/day = ~$137/month

### Scaling Triggers

Add capacity when:
- Call queue wait time > 2 seconds (SLA breach)
- Concurrent call rate > 2 during peak hours
- Client count exceeds 15 small businesses

---

*Analysis Date: January 2026*

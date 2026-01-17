# BuddyHelps - Comprehensive Build Plan

**Last Updated:** January 16, 2026

This document tracks everything that needs to be built to complete the BuddyHelps voice AI system.

---

## System Overview

BuddyHelps consists of two main projects:

| Project | Purpose | Location |
|---------|---------|----------|
| **buddyhelps-runpod** | Voice AI inference (STT/LLM/TTS) + Twilio call handling | `/home/cameronobrien/Documents/GitHub/buddyhelps-runpod` |
| **buddyhelps-dashboard** | Admin UI + public pages (call details, photo upload) | `/home/cameronobrien/Documents/GitHub/buddyhelps-dashboard` |

**Architecture doc:** `buddyhelps-dashboard/architecture.html`

---

## What's Built (Working Now)

### RunPod (Voice AI Server)

| Component | Status | Details |
|-----------|--------|---------|
| STT (Speech-to-Text) | ✅ Live | 4x faster-whisper pool, 150-180ms, 4 concurrent |
| LLM (Language Model) | ✅ Live | Qwen 0.5B via vLLM, 15-30ms |
| TTS (Text-to-Speech) | ✅ Live | Kokoro-82M, ~100ms |
| /pipeline endpoint | ✅ Live | Full STT→LLM→TTS in ~280ms |
| Admin UI | ✅ Live | 3 tabs: Numbers, Prompts, Keywords |
| SQLite database | ✅ Live | Phone configs, prompts, corrections |
| Keyword corrections | ✅ Live | Post-STT fixes (quogged→clogged) |
| Demo vs Live prompts | ✅ Live | is_demo flag for testing |

### Dashboard (Vercel)

| Component | Status | Details |
|-----------|--------|---------|
| Pod management UI | ✅ Live | View/manage RunPod pods |
| Twilio number management | ✅ Live | Buy, import, configure webhook |
| System prompts CRUD | ✅ Live | Reusable prompt templates |
| Keyword corrections CRUD | ✅ Live | STT post-processing rules |
| /api/call-complete | ✅ Live | Stores call, sends notifications |
| /c/[callId] page | ✅ Live | Call details (mobile-first) |
| /photo/[token] page | ✅ Live | Photo upload (1hr expiry) |
| Turso database | ✅ Live | Call records storage |
| Vercel Blob | ✅ Live | Photo storage |

---

## What's NOT Built Yet

### Priority 1: Core (Make Calls Work)

These are required for the system to handle real phone calls.

#### 1.1 Twilio WebSocket Handler
**Project:** buddyhelps-runpod
**File:** `src/twilio_ws.py` (new)
**Priority:** 🔴 Critical

Receives real-time audio stream from Twilio via WebSocket.

```python
# What it needs to do:
# 1. Accept WebSocket connection from Twilio
# 2. Receive audio chunks (base64 encoded, 8kHz mulaw)
# 3. Buffer audio until speech pause detected
# 4. Send to STT → LLM → TTS pipeline
# 5. Stream TTS audio back to Twilio
# 6. Handle call events (start, end, DTMF)
```

**Twilio Media Streams docs:** https://www.twilio.com/docs/voice/media-streams

**Key considerations:**
- Audio format: 8kHz mulaw (need to convert to 16kHz PCM for whisper)
- Bidirectional: receive customer audio, send AI audio
- Handle interruptions (barge-in)
- Track conversation state per call

---

#### 1.2 Audio Format Conversion
**Project:** buddyhelps-runpod
**File:** `src/audio_utils.py` (new)
**Priority:** 🔴 Critical

Convert between Twilio's format and what our models expect.

```python
def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """Convert 8kHz mulaw to 16kHz PCM for whisper."""
    pass

def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16kHz PCM from TTS to 8kHz mulaw for Twilio."""
    pass
```

**Libraries:**
- `audioop` (Python stdlib) for mulaw conversion
- `scipy.signal.resample` for sample rate conversion

---

#### 1.3 Twilio Webhook Handlers
**Project:** buddyhelps-runpod
**File:** `src/twilio_handlers.py` (new)
**Priority:** 🔴 Critical

HTTP endpoints Twilio calls when events happen.

| Endpoint | Purpose |
|----------|---------|
| `POST /incoming-call` | Called when someone dials. Returns TwiML to start Media Stream. |
| `POST /call-status` | Called when call status changes (ringing, answered, completed). |

**TwiML for Media Streams:**
```xml
<Response>
  <Connect>
    <Stream url="wss://your-runpod-url/ws/twilio" />
  </Connect>
</Response>
```

---

#### 1.4 Call State Management
**Project:** buddyhelps-runpod
**File:** `src/call_state.py` (new)
**Priority:** 🔴 Critical

Track active calls and their conversation state.

```python
class CallState:
    call_sid: str
    phone_number: str  # Twilio number that received call
    caller_number: str
    business_config: dict  # From database lookup
    conversation_history: List[dict]  # Messages for LLM context
    transcript: List[dict]  # Full transcript with timestamps
    started_at: datetime

# In-memory dict of active calls
active_calls: Dict[str, CallState] = {}
```

---

### Priority 2: Post-Call (Notifications)

After a call ends, notify the plumber and enable photo upload.

#### 2.1 Post-Call Webhook to Dashboard
**Project:** buddyhelps-runpod
**File:** `src/post_call.py` (new)
**Priority:** 🟡 High

When call ends, send data to dashboard's `/api/call-complete`.

```python
async def handle_call_complete(call_state: CallState):
    """Called when Twilio reports call ended."""

    # 1. Extract structured data from transcript
    extraction = await extract_call_info(call_state.transcript)

    # 2. POST to dashboard
    await httpx.post(
        "https://info.bennyhelps.ca/api/call-complete",
        json={
            "caller_name": extraction.get("customer_name"),
            "caller_phone": call_state.caller_number,
            "problem": extraction.get("problem"),
            "urgency": extraction.get("urgency"),
            "transcript": format_transcript(call_state.transcript),
            "business_name": call_state.business_config["business_name"],
            "plumber_phone": call_state.business_config["plumber_phone"],
            "plumber_email": call_state.business_config["plumber_email"],
            "twilio_number": call_state.phone_number,
        }
    )
```

---

#### 2.2 /extract Endpoint
**Project:** buddyhelps-runpod
**File:** `src/main.py` (add endpoint)
**Priority:** 🟡 High

Use LLM to extract structured data from conversation.

```python
EXTRACTION_PROMPT = """You extract information from plumbing service calls.

From this conversation, return JSON with:
- customer_name: string or null
- problem: short description
- urgency: "emergency", "soon", or "routine"
- location: room/area or null
- phone: callback number or null
- notes: anything else important

Return ONLY valid JSON. No other text."""

@app.post("/extract")
async def extract_call_info(request: ExtractionRequest):
    result = llm.generate(
        messages=request.conversation_history,
        system_prompt=EXTRACTION_PROMPT,
        temperature=0.1,  # Low for consistent JSON
    )
    return json.loads(result)
```

**Note:** Reuses existing Qwen 0.5B instance. No extra VRAM.

---

#### 2.3 Call Logging Table
**Project:** buddyhelps-runpod
**File:** `src/database.py` (add table)
**Priority:** 🟡 High

Store completed calls locally (backup, debugging).

```sql
CREATE TABLE call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid TEXT UNIQUE,
    phone_number TEXT,           -- Twilio number
    caller_number TEXT,
    business_name TEXT,
    transcript TEXT,             -- JSON
    extracted_data TEXT,         -- JSON
    dashboard_notified INTEGER DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

### Priority 3: Scale & Monitoring

#### 3.1 Health Monitoring
**Project:** buddyhelps-dashboard
**Priority:** 🟠 Medium

Dashboard polls pods for health status.

| Metric | Source |
|--------|--------|
| Active calls | `/health` endpoint |
| STT queue depth | `/stt/stats` endpoint |
| Memory usage | RunPod API |
| Uptime | RunPod API |

---

### Priority 4: SaaS Features (Long-Term)

For when BuddyHelps becomes a self-signup SaaS product.

#### 4.1 Pod Assignment Logic
**Project:** buddyhelps-dashboard
**Priority:** ⚪ Future (SaaS)

Automatic pod assignment when businesses self-signup.

```javascript
// When new business signs up and picks a Twilio number:
// 1. Query all pods for current call count
// 2. Find pod with most available capacity
// 3. Configure Twilio webhook to that pod
// 4. Store assignment in database
```

**Why this matters for SaaS:**
- Self-signup means you can't manually assign pods
- Auto-scaling: spin up new pods when capacity hits threshold
- Load balancing across pods for reliability

**Not needed now:** Manual assignment works fine with direct sales model.

---

### Priority 5: Future Features

Nice-to-haves after core system works.

#### 5.1 Photo Upload via SMS (During Call)
**Priority:** ⚪ Low

AI tells customer: "I'll text you a link to send photos."
Triggers SMS immediately during call, not just after.

---

#### 5.2 Voicemail Mode
**Priority:** ⚪ Low

If AI can't help, offer to take a message.

---

#### 5.3 Call Recording
**Priority:** ⚪ Low

Store audio recordings (requires Twilio recording + storage).

---

#### 5.4 Analytics Dashboard
**Priority:** ⚪ Low

- Calls per day/week
- Average call duration
- Common problem types
- Urgency distribution

---

## Build Order (Recommended)

```
Phase 1: Make Calls Work
├── 1.1 Twilio WebSocket handler
├── 1.2 Audio format conversion
├── 1.3 Twilio webhook handlers
└── 1.4 Call state management

Phase 2: Post-Call Processing
├── 2.1 Post-call webhook to dashboard
├── 2.2 /extract endpoint (+ inline function)
└── 2.3 Call logging table

Phase 3: Test End-to-End
├── Test with Cameron's number (+18255563359)
├── Verify SMS received
├── Verify photo upload works
└── Verify call details page works

Phase 4: Monitoring
└── 3.1 Health monitoring

Phase 5: SaaS (when ready to scale)
└── 4.1 Pod assignment logic (self-signup)
```

---

## Testing Checklist

### Phase 1 Complete When:
- [ ] Can dial Twilio number
- [ ] AI answers and speaks greeting
- [ ] AI hears customer and responds
- [ ] Conversation flows naturally
- [ ] Call ends cleanly

### Phase 2 Complete When:
- [ ] Plumber receives SMS after call
- [ ] SMS contains problem summary + link
- [ ] Customer receives photo upload link
- [ ] Photos appear on call details page

### Full System Complete When:
- [ ] Multiple plumbers can use system simultaneously
- [ ] Each plumber gets their own phone number
- [ ] Calls route to correct business config
- [ ] Notifications go to correct plumber

---

## Environment Variables Needed

### RunPod (.env)
```bash
# Already have:
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+15874059371

# Need to add:
DASHBOARD_WEBHOOK_URL=https://info.bennyhelps.ca/api/call-complete
DASHBOARD_WEBHOOK_SECRET=...  # Optional: sign webhooks
```

### Dashboard (Vercel)
```bash
# Already have:
TURSO_DATABASE_URL=...
TURSO_AUTH_TOKEN=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
RESEND_API_KEY=...
```

---

## Related Documents

- **Architecture:** `buddyhelps-dashboard/architecture.html`
- **Post-Call Processing:** `buddyhelps-runpod/docs/POST_CALL_PROCESSING.md`
- **Concurrency Analysis:** `buddyhelps-runpod/docs/CONCURRENCY_ANALYSIS.md`
- **Dashboard Notes:** `buddyhelps-dashboard/NOTES.md`
- **RunPod Notes:** `buddyhelps-runpod/NOTES.md`

---

*This is the single source of truth for what needs to be built.*

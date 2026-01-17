# BuddyHelps - Post-Call Processing

## Purpose

After a call ends, extract structured data from the conversation transcript and send SMS/email summaries to the plumber client.

---

## Key Finding: LLM Reuse

**Yes, we can reuse the same Qwen 0.5B vLLM instance.** The architecture already supports this:

```python
# llm.py already accepts custom system_prompt
llm.generate(
    messages=conversation_history,
    system_prompt=EXTRACTION_PROMPT,  # Different prompt, same model
    temperature=0.1,  # Lower for consistent JSON output
)
```

- `_llm` is a singleton (cached global variable)
- No additional VRAM needed
- No model reloading
- Just pass a different `system_prompt`

---

## Implementation

### 1. Extraction Prompt (Qwen 0.5B adapted)

```
You extract information from plumbing service calls.

From this conversation, return JSON with:
- customer_name: string or null
- problem: short description
- urgency: "emergency", "soon", or "routine"
- location: room/area or null
- phone: callback number or null
- notes: anything else important

Return ONLY valid JSON. No other text.
```

**Design notes:**
- Keep it short (Qwen 0.5B has limited reasoning)
- Explicit JSON field names
- Use low temperature (0.1) for consistent output
- "or null" makes fields optional gracefully

### 2. New Endpoint: `/extract`

```python
@app.post("/extract")
async def extract_call_info(request: ExtractionRequest):
    """Extract structured data from completed call transcript."""

    extraction_prompt = """You extract information from plumbing service calls...."""

    result = llm.generate(
        messages=request.conversation_history,
        system_prompt=extraction_prompt,
        max_tokens=200,
        temperature=0.1,
    )

    try:
        data = json.loads(result)
        return data
    except json.JSONDecodeError:
        # Fallback: return raw text if JSON parsing fails
        return {"raw": result, "parse_error": True}
```

### 3. Database Table: `call_extractions`

```sql
CREATE TABLE call_extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT UNIQUE,                    -- External reference
    phone_number TEXT,                      -- Twilio number that received call
    conversation_json TEXT,                 -- Full transcript
    extracted_data TEXT,                    -- JSON extraction result
    sms_sent INTEGER DEFAULT 0,
    email_sent INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

### 4. Notification Delivery

**SMS via Twilio:**
```python
def send_sms_summary(to_number: str, extraction: dict):
    message = f"""New call from {extraction.get('phone', 'unknown')}
Problem: {extraction.get('problem', 'N/A')}
Urgency: {extraction.get('urgency', 'N/A')}
Location: {extraction.get('location', 'N/A')}"""

    twilio_client.messages.create(
        body=message,
        from_=settings.twilio_number,
        to=to_number
    )
```

**Email via Resend:**
```python
def send_email_summary(to_email: str, extraction: dict):
    resend.Emails.send({
        "from": "benny@bennyhelps.ca",
        "to": to_email,
        "subject": f"New Call: {extraction.get('problem', 'Service Request')}",
        "html": render_email_template(extraction)
    })
```

---

## Call Flow (When Built)

```
1. Twilio WebSocket → receives audio
2. STT (faster-whisper) → transcribes in real-time
3. LLM (conversation prompt) → generates responses
4. TTS (Kokoro) → speaks responses
5. Call ends
6. /extract endpoint → extracts structured data
7. Store extraction in database
8. Send SMS + email to plumber
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/main.py` | Add `/extract` endpoint |
| `src/database.py` | Add `call_extractions` table |
| `src/notifications.py` | **New** - SMS + email delivery |
| `prompts/extraction.txt` | **New** - Extraction prompt template |

---

## Not Building Now

Per Cameron: "we don't need to build that now"

This plan documents the approach for future reference. Key insight validated: **same LLM instance, different prompt** works perfectly.

---

## Verification (When Built)

1. Make a test call with known conversation
2. Call `/extract` with the transcript
3. Verify JSON output has correct fields
4. Check SMS received by test number
5. Check email delivered

---

## Cost/Performance

| Step | Time | Cost |
|------|------|------|
| Extraction LLM | ~20-30ms | $0 (self-hosted) |
| Twilio SMS | instant | ~$0.0079/message |
| Resend Email | instant | Free tier (3k/month) |

**Total per call:** ~$0.01 for notification delivery

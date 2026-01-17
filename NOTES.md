# BuddyHelps RunPod - Session Notes

### 2026-01-15 - Major STT Architecture Change

**Summary:** Replaced single-instance Parakeet STT with 4x faster-whisper pool for 4x concurrent call capacity.

**Completed:**
- [x] Implemented multi-instance faster-whisper STT pool (`src/stt_whisper.py`)
- [x] Added keyword corrections system (STT post-processing)
- [x] Added system prompts management (reusable templates)
- [x] Created tabbed admin UI (Phone Numbers, System Prompts, Keywords)
- [x] Updated pipeline to apply keyword corrections between STT and LLM
- [x] Deployed to RunPod and verified healthy

**Key Decisions:**
- **4x faster-whisper base over Parakeet** - Trades 64ms latency for 150-180ms but gains 4x concurrency. Net win for multi-tenant.
- **First-available instance selection** - Better than round-robin because it minimizes wait time for variable-length audio.
- **Not adding second TTS** - TTS only runs per AI response (~10x per call), queuing is rare. Save VRAM for more STT instances if needed.

**Architecture Changes:**

| Before | After |
|--------|-------|
| Parakeet (1 instance, 64ms) | faster-whisper (4 instances, 150-180ms) |
| 1-2 concurrent calls | 4 concurrent calls |
| 10-20 plumbers | 40-60 plumbers |
| No keyword corrections | Keyword corrections (quogged→clogged) |
| Hardcoded prompts | Configurable system prompts |

**Files Created:**
- `src/stt_whisper.py` - Multi-instance whisper pool with thread-safe locking
- `src/stt_corrections.py` - Regex-based keyword corrections
- `docs/CONCURRENCY_ANALYSIS.md` - Capacity analysis with plumber math

**Files Modified:**
- `src/config.py` - Added STT backend selection and whisper settings
- `src/main.py` - Conditional STT loading, new /stt/stats endpoint
- `src/database.py` - Added keyword_corrections table, CRUD functions
- `src/admin.py` - Added Keywords tab, prompts API
- `requirements.txt` - Added faster-whisper, commented out nemo_toolkit

**Capacity Math:**
- Solo plumber: ~5 calls/day, spread over 8 hours
- With 4 concurrent STT: Can serve 40-60 solo plumbers
- Cost per client drops from $9-14 to $2-4/month

**Next Session:**
- [ ] Wire up Twilio WebSocket handler for real phone calls
- [ ] Test with actual phone audio (8kHz mulaw preprocessing)
- [ ] Monitor STT pool stats under load

---

### 2026-01-15 - Demo vs Live Prompts

**Summary:** Added Demo Mode and Live Plumbing prompts adapted for Qwen 0.5B model size.

**Completed:**
- [x] Added `is_demo` field to phone_numbers table for explicit demo/live detection
- [x] Created Demo Mode prompt (for plumbers testing the system)
- [x] Created Live Plumbing prompt (for real customer service calls)
- [x] Updated LLM to support `{greeting_name}` placeholder
- [x] Updated admin UI with Mode column and is_demo checkbox
- [x] Deployed to RunPod and verified healthy

**Key Decisions:**
- **Adapted prompts for Qwen 0.5B** - Shorter, more explicit instructions. No function calling (model too small).
- **is_demo field on phone_numbers** - Explicit flag instead of detecting from phone number list.
- **Three default prompts** - Default Plumber (basic), Demo Mode (testing), Live Plumbing (real calls)

**Prompts Created:**
1. **Default Plumber** - Basic conversational prompt
2. **Demo Mode** - Role-play for plumbers testing: greet, explain demo, handle fake problem, direct to bennyhelps.ca
3. **Live Plumbing** - Real customer calls: collect problem, location, urgency, callback info

**Future Work:**
- [ ] Parse call transcript to extract structured data (problem, urgency, contact info)
- [ ] Send SMS/email summary to client after call ends
- [ ] Use same vLLM instance with extraction prompt (validated: works, see plan file)

**Post-Call Processing Plan:** `docs/POST_CALL_PROCESSING.md`
- Same Qwen 0.5B instance, just different `system_prompt`
- No extra VRAM, no model reload, ~20-30ms per extraction
- SMS via Twilio (~$0.008/msg), Email via Resend (free tier)

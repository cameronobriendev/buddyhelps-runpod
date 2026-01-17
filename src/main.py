"""
BuddyHelps Voice Server - FastAPI Application

Endpoints for STT, LLM, TTS, full pipeline processing, and Twilio call handling.
"""
import logging
import time
from typing import List, Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, WebSocket
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from .config import settings
from . import llm, tts, database as db
from .admin import router as admin_router
from .stt_corrections import apply_corrections
from .twilio_handlers import router as twilio_router
from .twilio_ws import handle_twilio_websocket
from .call_state import call_manager

# Conditional STT import based on backend setting
if settings.stt_backend == "whisper":
    from . import stt_whisper as stt
else:
    from . import stt

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup."""
    logger.info("Starting BuddyHelps Voice Server...")

    # Initialize database
    logger.info("Initializing database...")
    db.init_db()

    # Load STT based on backend setting
    if settings.stt_backend == "whisper":
        logger.info(f"Loading STT (faster-whisper pool: {settings.whisper_num_instances}x {settings.whisper_model_size})...")
        stt.load_model(
            model_size=settings.whisper_model_size,
            num_instances=settings.whisper_num_instances,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    else:
        logger.info("Loading STT model (Parakeet)...")
        stt.load_model(settings.stt_model)
    stt.warmup()

    logger.info("Loading LLM model...")
    llm.load_model(settings.llm_model)

    logger.info("Loading TTS model...")
    tts.load_model()

    logger.info("All models loaded and ready!")
    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="BuddyHelps Voice Server",
    description="Self-hosted voice AI inference for BuddyHelps",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(admin_router)
app.include_router(twilio_router)


# WebSocket endpoint for Twilio Media Streams
@app.websocket("/ws/twilio")
async def twilio_websocket(websocket: WebSocket):
    """Handle Twilio Media Stream WebSocket connections."""
    await handle_twilio_websocket(websocket)


# Request/Response Models
class LLMRequest(BaseModel):
    messages: List[Dict[str, str]]
    business_name: str = "the plumbing company"
    owner_name: str = "the owner"
    max_tokens: int = 256
    temperature: float = 0.7


class LLMResponse(BaseModel):
    text: str
    latency_ms: float


class TTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0


class PipelineRequest(BaseModel):
    business_name: str
    owner_name: str
    conversation_history: List[Dict[str, str]] = []


class HealthResponse(BaseModel):
    status: str
    models_loaded: bool
    stt_ready: bool
    llm_ready: bool
    tts_ready: bool
    active_calls: int


# Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server health and model status."""
    # Check STT ready based on backend
    if settings.stt_backend == "whisper":
        stt_ready = stt._pool is not None
    else:
        stt_ready = stt._model is not None

    return HealthResponse(
        status="healthy",
        models_loaded=True,
        stt_ready=stt_ready,
        llm_ready=llm._model is not None,
        tts_ready=tts._pipeline is not None,
        active_calls=call_manager.get_active_count(),
    )


@app.get("/stt/stats")
async def stt_stats():
    """Get STT pool statistics (whisper backend only)."""
    if settings.stt_backend == "whisper":
        return stt.get_stats()
    return {"backend": "parakeet", "message": "Stats not available for Parakeet"}


@app.post("/stt")
async def speech_to_text(file: UploadFile = File(...)):
    """
    Transcribe audio file to text.

    Accepts WAV audio (16kHz mono preferred).
    """
    start = time.perf_counter()

    try:
        audio_bytes = await file.read()
        text = stt.transcribe_bytes(audio_bytes)
        latency_ms = (time.perf_counter() - start) * 1000

        return JSONResponse({
            "text": text,
            "latency_ms": round(latency_ms, 2),
        })
    except Exception as e:
        logger.error(f"STT error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/llm", response_model=LLMResponse)
async def generate_response(request: LLMRequest):
    """
    Generate LLM response for conversation.
    """
    start = time.perf_counter()

    try:
        text = llm.generate(
            messages=request.messages,
            business_name=request.business_name,
            owner_name=request.owner_name,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        return LLMResponse(
            text=text,
            latency_ms=round(latency_ms, 2),
        )
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Synthesize speech from text.

    Returns WAV audio.
    """
    start = time.perf_counter()

    try:
        audio_bytes = tts.synthesize_to_bytes(
            text=request.text,
            voice=request.voice,
            speed=request.speed,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "X-Latency-Ms": str(round(latency_ms, 2)),
            },
        )
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts/voices")
async def list_voices():
    """List available TTS voice presets."""
    return tts.list_voices()


@app.post("/pipeline")
async def full_pipeline(
    file: UploadFile = File(...),
    business_name: str = Query(...),
    owner_name: str = Query(...),
    conversation_history: str = Query(default="[]"),
    phone_number: str = Query(default=None),
):
    """
    Full voice pipeline: STT -> Keyword Corrections -> LLM -> TTS

    1. Transcribe incoming audio
    2. Apply keyword corrections (if phone_number provided)
    3. Generate response with LLM
    4. Synthesize response to speech

    If phone_number is provided, uses the configured system_prompt and keyword_corrections.
    Returns WAV audio of the response.
    """
    import json

    total_start = time.perf_counter()

    try:
        # Parse conversation history
        history = json.loads(conversation_history)

        # Look up config if phone number provided
        config = None
        keyword_corrections = {}
        system_prompt = None
        greeting_name = "Benny"

        if phone_number:
            config = db.get_config_for_call(phone_number)
            if config:
                keyword_corrections = config.get('keyword_corrections', {})
                system_prompt = config.get('system_prompt') or None
                greeting_name = config.get('greeting_name', greeting_name)
                # Use config values if not overridden
                if not business_name:
                    business_name = config.get('business_name', business_name)

        # STT
        stt_start = time.perf_counter()
        audio_bytes = await file.read()
        user_text_raw = stt.transcribe_bytes(audio_bytes)
        stt_ms = (time.perf_counter() - stt_start) * 1000

        # Apply keyword corrections
        user_text = apply_corrections(user_text_raw, keyword_corrections)
        corrections_applied = user_text != user_text_raw

        # Add user message to history
        history.append({"role": "user", "content": user_text})

        # LLM
        llm_start = time.perf_counter()
        response_text = llm.generate(
            messages=history,
            business_name=business_name,
            owner_name=owner_name,
            greeting_name=greeting_name,
            system_prompt=system_prompt,
        )
        llm_ms = (time.perf_counter() - llm_start) * 1000

        # TTS
        tts_start = time.perf_counter()
        response_audio = tts.synthesize_to_bytes(response_text)
        tts_ms = (time.perf_counter() - tts_start) * 1000

        total_ms = (time.perf_counter() - total_start) * 1000

        return Response(
            content=response_audio,
            media_type="audio/wav",
            headers={
                "X-User-Text-Raw": user_text_raw[:100],
                "X-User-Text": user_text[:100],
                "X-Corrections-Applied": str(corrections_applied),
                "X-Response-Text": response_text[:100],
                "X-STT-Ms": str(round(stt_ms, 2)),
                "X-LLM-Ms": str(round(llm_ms, 2)),
                "X-TTS-Ms": str(round(tts_ms, 2)),
                "X-Total-Ms": str(round(total_ms, 2)),
            },
        )
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )

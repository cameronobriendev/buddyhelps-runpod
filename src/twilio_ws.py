"""
Twilio Media Streams WebSocket handler.

Handles real-time bidirectional audio streaming with Twilio.
"""
import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

from .audio_utils import (
    AudioBuffer,
    detect_speech_end,
    mulaw_to_pcm16k,
    pcm_to_mulaw8k,
    pcm_to_wav_bytes,
)
from .call_state import CallState, CallStatus, call_manager
from .stt_corrections import apply_corrections
from . import database as db

# Conditional imports based on STT backend
from .config import settings
if settings.stt_backend == "whisper":
    from . import stt_whisper as stt
else:
    from . import stt

from . import llm, tts

logger = logging.getLogger(__name__)

# Constants
SILENCE_THRESHOLD = 500          # RMS threshold for silence detection
SILENCE_DURATION_MS = 700        # ms of silence before processing
MIN_SPEECH_MS = 300              # Minimum speech duration to process
CHUNK_DURATION_MS = 20           # Twilio sends 20ms chunks


class TwilioMediaHandler:
    """Handles a single Twilio Media Stream WebSocket connection."""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.call_state: Optional[CallState] = None
        self.audio_buffer = AudioBuffer(min_duration_ms=100)  # Small buffer, we use VAD
        self.stream_sid: Optional[str] = None

        # Voice activity detection state
        self.speech_chunks = bytearray()  # Accumulated speech
        self.silence_start: Optional[float] = None
        self.is_user_speaking = False

        # Prevent overlapping responses
        self.is_processing = False
        self.pending_interrupt = False

    async def handle_connection(self):
        """Main WebSocket handler loop."""
        try:
            await self.websocket.accept()
            logger.info("Twilio WebSocket connected")

            async for message in self.websocket.iter_text():
                await self.handle_message(json.loads(message))

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {self.stream_sid}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def handle_message(self, msg: dict):
        """Route incoming Twilio messages."""
        event = msg.get("event")

        if event == "connected":
            logger.info("Twilio Media Stream connected")

        elif event == "start":
            await self.handle_start(msg)

        elif event == "media":
            await self.handle_media(msg)

        elif event == "stop":
            await self.handle_stop(msg)

        elif event == "mark":
            # Mark events indicate TTS playback completed
            await self.handle_mark(msg)

    async def handle_start(self, msg: dict):
        """Handle stream start - initialize call state."""
        start_data = msg.get("start", {})
        self.stream_sid = start_data.get("streamSid")
        call_sid = start_data.get("callSid")
        custom_params = start_data.get("customParameters", {})

        logger.info(f"Stream started: {self.stream_sid}, call: {call_sid}")

        # Get or create call state
        self.call_state = call_manager.get_call(call_sid)
        if not self.call_state:
            # Call state should have been created by webhook, but handle edge case
            twilio_number = custom_params.get("twilio_number", "")
            caller_number = custom_params.get("caller_number", "")
            self.call_state = call_manager.create_call(call_sid, twilio_number, caller_number)

        # Register stream
        call_manager.register_stream(self.stream_sid, call_sid)
        self.call_state.status = CallStatus.IN_PROGRESS
        self.call_state.answered_at = time.time()

        # Load business config from database
        await self.load_business_config()

        # Send initial greeting
        await self.send_greeting()

    async def load_business_config(self):
        """Load business config from database based on Twilio number."""
        if not self.call_state:
            return

        config = db.get_config_for_call(self.call_state.twilio_number)
        if config:
            self.call_state.business_name = config.get("business_name", "")
            self.call_state.owner_name = config.get("owner_name", "")
            self.call_state.greeting_name = config.get("greeting_name", "Benny")
            self.call_state.system_prompt = config.get("system_prompt")
            self.call_state.keyword_corrections = config.get("keyword_corrections", {})
            self.call_state.plumber_phone = config.get("plumber_phone", "")
            self.call_state.plumber_email = config.get("plumber_email", "")
            self.call_state.is_demo = config.get("is_demo", False)
            logger.info(f"Loaded config for {self.call_state.twilio_number}: {self.call_state.business_name}")
        else:
            logger.warning(f"No config found for number: {self.call_state.twilio_number}")

    async def send_greeting(self):
        """Send initial greeting to customer."""
        if not self.call_state:
            return

        # Generate greeting based on business config
        if self.call_state.is_demo:
            greeting = f"Hi! This is {self.call_state.greeting_name}, a demo of the BuddyHelps voice assistant. I'm here to show you how I can help answer calls for your business. Go ahead and pretend you're a customer calling with a plumbing issue!"
        else:
            business = self.call_state.business_name or "the business"
            greeting = f"Hi, thanks for calling {business}! This is {self.call_state.greeting_name}. How can I help you today?"

        await self.speak(greeting)
        self.call_state.add_assistant_message(greeting)

    async def handle_media(self, msg: dict):
        """Handle incoming audio from customer."""
        if not self.call_state or self.call_state.status != CallStatus.IN_PROGRESS:
            return

        media = msg.get("media", {})
        payload = media.get("payload")  # Base64 mulaw audio

        if not payload:
            return

        # Convert to PCM
        pcm = mulaw_to_pcm16k(payload)

        # Voice activity detection
        is_silence = detect_speech_end(pcm, threshold=SILENCE_THRESHOLD)

        if not is_silence:
            # Speech detected
            self.speech_chunks.extend(pcm)
            self.silence_start = None
            self.is_user_speaking = True

            # If AI is speaking and user interrupts, mark for interrupt
            if self.call_state.is_speaking:
                self.pending_interrupt = True

        else:
            # Silence detected
            if self.is_user_speaking:
                if self.silence_start is None:
                    self.silence_start = time.time()
                elif (time.time() - self.silence_start) * 1000 >= SILENCE_DURATION_MS:
                    # Enough silence after speech - process
                    if len(self.speech_chunks) > MIN_SPEECH_MS * 32:  # 16kHz * 2 bytes * ms/1000
                        await self.process_speech()
                    self.reset_audio_state()

    async def process_speech(self):
        """Process accumulated speech through STT -> LLM -> TTS pipeline."""
        if not self.call_state or self.is_processing:
            return

        self.is_processing = True
        start_time = time.time()

        try:
            # Convert to WAV for STT
            pcm_bytes = bytes(self.speech_chunks)
            wav_bytes = pcm_to_wav_bytes(pcm_bytes, sample_rate=16000)

            # STT
            stt_start = time.time()
            text_raw = stt.transcribe_bytes(wav_bytes)
            stt_ms = (time.time() - stt_start) * 1000
            logger.info(f"STT ({stt_ms:.0f}ms): {text_raw}")

            if not text_raw or len(text_raw.strip()) < 2:
                logger.debug("Empty or too short transcription, skipping")
                return

            # Apply keyword corrections
            text = apply_corrections(text_raw, self.call_state.keyword_corrections)
            if text != text_raw:
                logger.debug(f"Corrected: {text_raw} -> {text}")

            # Add to conversation
            self.call_state.add_user_message(text)

            # Check for interrupt before LLM
            if self.pending_interrupt:
                logger.info("Interrupt detected, skipping response")
                self.pending_interrupt = False
                return

            # LLM
            llm_start = time.time()
            response = llm.generate(
                messages=self.call_state.conversation_history,
                business_name=self.call_state.business_name,
                owner_name=self.call_state.owner_name,
                greeting_name=self.call_state.greeting_name,
                system_prompt=self.call_state.system_prompt,
            )
            llm_ms = (time.time() - llm_start) * 1000
            logger.info(f"LLM ({llm_ms:.0f}ms): {response}")

            # Check for interrupt before TTS
            if self.pending_interrupt:
                logger.info("Interrupt detected, skipping TTS")
                self.pending_interrupt = False
                return

            # Speak response
            await self.speak(response)
            self.call_state.add_assistant_message(response)

            total_ms = (time.time() - start_time) * 1000
            logger.info(f"Pipeline total: {total_ms:.0f}ms")

        except Exception as e:
            logger.error(f"Error processing speech: {e}", exc_info=True)
        finally:
            self.is_processing = False

    async def speak(self, text: str):
        """Convert text to speech and send to Twilio."""
        if not self.call_state:
            return

        self.call_state.is_speaking = True

        try:
            # Generate TTS
            tts_start = time.time()
            audio_bytes = tts.synthesize_to_bytes(text)
            tts_ms = (time.time() - tts_start) * 1000
            logger.debug(f"TTS ({tts_ms:.0f}ms): {len(audio_bytes)} bytes")

            # Convert to Twilio format (24kHz PCM -> 8kHz mulaw)
            mulaw_b64 = pcm_to_mulaw8k(audio_bytes, input_rate=24000)

            # Send to Twilio
            await self.send_audio(mulaw_b64)

            # Send mark to know when playback finishes
            await self.send_mark("speech_end")

        except Exception as e:
            logger.error(f"Error in TTS: {e}", exc_info=True)
            self.call_state.is_speaking = False

    async def send_audio(self, mulaw_b64: str):
        """Send audio chunk to Twilio."""
        if not self.stream_sid:
            return

        message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {
                "payload": mulaw_b64
            }
        }
        await self.websocket.send_json(message)

    async def send_mark(self, name: str):
        """Send mark event to track playback."""
        if not self.stream_sid:
            return

        message = {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {
                "name": name
            }
        }
        await self.websocket.send_json(message)

    async def handle_mark(self, msg: dict):
        """Handle mark event - TTS playback completed."""
        mark = msg.get("mark", {})
        name = mark.get("name")

        if name == "speech_end" and self.call_state:
            self.call_state.is_speaking = False
            logger.debug("Speech playback completed")

    async def handle_stop(self, msg: dict):
        """Handle stream stop - call ending."""
        logger.info(f"Stream stopping: {self.stream_sid}")

        if self.call_state:
            self.call_state.status = CallStatus.COMPLETED

    def reset_audio_state(self):
        """Reset audio buffering state."""
        self.speech_chunks.clear()
        self.silence_start = None
        self.is_user_speaking = False

    async def cleanup(self):
        """Clean up after WebSocket closes."""
        if self.call_state:
            call_sid = self.call_state.call_sid
            call_manager.end_call(call_sid)
            # Note: Don't remove call yet - post_call.py will handle that after processing
            logger.info(f"Call cleanup: {call_sid}")


async def handle_twilio_websocket(websocket: WebSocket):
    """Entry point for Twilio WebSocket connections."""
    handler = TwilioMediaHandler(websocket)
    await handler.handle_connection()

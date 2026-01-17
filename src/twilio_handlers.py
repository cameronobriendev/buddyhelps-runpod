"""
Twilio HTTP webhook handlers.

These endpoints are called by Twilio when calls come in and when call status changes.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import PlainTextResponse

from .call_state import call_manager, CallStatus
from .config import settings
from . import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])


def generate_twiml_connect(websocket_url: str, call_sid: str, twilio_number: str, caller_number: str) -> str:
    """
    Generate TwiML to connect call to Media Stream.

    Args:
        websocket_url: Full WebSocket URL for media stream
        call_sid: Twilio call SID
        twilio_number: The BuddyHelps number that was called
        caller_number: The customer's phone number
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}">
            <Parameter name="call_sid" value="{call_sid}" />
            <Parameter name="twilio_number" value="{twilio_number}" />
            <Parameter name="caller_number" value="{caller_number}" />
        </Stream>
    </Connect>
</Response>"""


def generate_twiml_reject(reason: str = "rejected") -> str:
    """Generate TwiML to reject a call."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Reject reason="{reason}" />
</Response>"""


def generate_twiml_say(message: str) -> str:
    """Generate TwiML to say a message and hang up."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Matthew">{message}</Say>
    <Hangup />
</Response>"""


@router.post("/incoming-call")
async def incoming_call(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    CallStatus: str = Form(default="ringing"),
):
    """
    Handle incoming call from Twilio.

    This is the voice_url webhook that Twilio calls when someone dials a number.
    Returns TwiML to connect the call to our WebSocket media stream.
    """
    logger.info(f"Incoming call: {CallSid} from {From} to {To}")

    # Check if we have config for this number
    config = db.get_config_for_call(To)
    if not config:
        logger.warning(f"No config for number {To}, rejecting call")
        return Response(
            content=generate_twiml_say("Sorry, this number is not configured. Please try again later."),
            media_type="application/xml"
        )

    # Check if number is active
    if not config.get("is_active", True):
        logger.warning(f"Number {To} is not active, rejecting call")
        return Response(
            content=generate_twiml_say("Sorry, this service is temporarily unavailable. Please try again later."),
            media_type="application/xml"
        )

    # Create call state
    call_state = call_manager.create_call(
        call_sid=CallSid,
        twilio_number=To,
        caller_number=From,
    )

    # Build WebSocket URL
    # Use the RunPod proxy URL for WebSocket
    # Format: wss://[pod-id]-[port].proxy.runpod.net/ws/twilio
    host = request.headers.get("host", "")

    # Handle both local development and RunPod deployment
    if "runpod.net" in host:
        # RunPod - use wss
        ws_url = f"wss://{host}/ws/twilio"
    elif "localhost" in host or "127.0.0.1" in host:
        # Local development - use ws
        ws_url = f"ws://{host}/ws/twilio"
    else:
        # Fallback - try to construct from settings
        ws_url = f"wss://{host}/ws/twilio"

    logger.info(f"Connecting call {CallSid} to WebSocket: {ws_url}")

    # Return TwiML to connect to media stream
    twiml = generate_twiml_connect(
        websocket_url=ws_url,
        call_sid=CallSid,
        twilio_number=To,
        caller_number=From,
    )

    return Response(content=twiml, media_type="application/xml")


@router.post("/call-status")
async def call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    From: str = Form(default=""),
    To: str = Form(default=""),
    CallDuration: Optional[str] = Form(default=None),
    Timestamp: Optional[str] = Form(default=None),
):
    """
    Handle call status updates from Twilio.

    Called when call status changes (ringing, in-progress, completed, failed, etc.)
    """
    logger.info(f"Call status update: {CallSid} -> {CallStatus}")

    call_state = call_manager.get_call(CallSid)

    if CallStatus == "completed":
        if call_state:
            call_manager.end_call(CallSid)
            # Trigger post-call processing
            # This will be handled by post_call.py
            logger.info(f"Call completed: {CallSid}, duration: {CallDuration}s")

    elif CallStatus == "failed" or CallStatus == "busy" or CallStatus == "no-answer":
        if call_state:
            call_state.status = CallStatus.FAILED
            call_manager.remove_call(CallSid)
            logger.warning(f"Call failed: {CallSid}, status: {CallStatus}")

    return PlainTextResponse("OK")


@router.get("/health")
async def twilio_health():
    """Health check for Twilio integration."""
    return {
        "status": "ok",
        "active_calls": call_manager.get_active_count(),
    }

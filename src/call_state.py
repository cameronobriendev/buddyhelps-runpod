"""
Call state management for active calls.

Tracks conversation history, transcripts, and business config for each active call.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CallStatus(Enum):
    """Call lifecycle states."""
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CallState:
    """State for a single active call."""

    # Twilio identifiers
    call_sid: str
    stream_sid: Optional[str] = None

    # Phone numbers
    twilio_number: str = ""      # The BuddyHelps number that was called
    caller_number: str = ""      # The customer's phone number

    # Business config (loaded from database)
    business_name: str = ""
    owner_name: str = ""
    greeting_name: str = "Benny"
    system_prompt: Optional[str] = None
    keyword_corrections: Dict[str, str] = field(default_factory=dict)
    plumber_phone: str = ""      # For SMS notification
    plumber_email: str = ""      # For email notification
    is_demo: bool = False

    # Conversation state
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    status: CallStatus = CallStatus.RINGING

    # Transcript (for post-call processing)
    transcript: List[Dict] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    # Audio state
    is_speaking: bool = False    # Is AI currently speaking?
    pending_audio: List[str] = field(default_factory=list)  # Queued TTS chunks

    def add_user_message(self, text: str):
        """Add user (customer) message to conversation."""
        self.conversation_history.append({"role": "user", "content": text})
        self.transcript.append({
            "role": "customer",
            "text": text,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.debug(f"[{self.call_sid}] Customer: {text}")

    def add_assistant_message(self, text: str):
        """Add assistant (AI) message to conversation."""
        self.conversation_history.append({"role": "assistant", "content": text})
        self.transcript.append({
            "role": "assistant",
            "text": text,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.debug(f"[{self.call_sid}] Assistant: {text}")

    def get_duration_seconds(self) -> float:
        """Get call duration in seconds."""
        end = self.ended_at or datetime.utcnow()
        if self.answered_at:
            return (end - self.answered_at).total_seconds()
        return 0.0

    def format_transcript(self) -> str:
        """Format transcript for storage/display."""
        lines = []
        for entry in self.transcript:
            role = "Customer" if entry["role"] == "customer" else "Benny"
            lines.append(f"{role}: {entry['text']}")
        return "\n".join(lines)


class CallStateManager:
    """Manages all active calls."""

    def __init__(self):
        self._calls: Dict[str, CallState] = {}  # Keyed by call_sid
        self._stream_to_call: Dict[str, str] = {}  # stream_sid -> call_sid

    def create_call(self, call_sid: str, twilio_number: str, caller_number: str) -> CallState:
        """Create a new call state."""
        call = CallState(
            call_sid=call_sid,
            twilio_number=twilio_number,
            caller_number=caller_number,
        )
        self._calls[call_sid] = call
        logger.info(f"Created call state: {call_sid} from {caller_number} to {twilio_number}")
        return call

    def get_call(self, call_sid: str) -> Optional[CallState]:
        """Get call state by call SID."""
        return self._calls.get(call_sid)

    def get_call_by_stream(self, stream_sid: str) -> Optional[CallState]:
        """Get call state by stream SID."""
        call_sid = self._stream_to_call.get(stream_sid)
        if call_sid:
            return self._calls.get(call_sid)
        return None

    def register_stream(self, stream_sid: str, call_sid: str):
        """Associate a stream SID with a call SID."""
        self._stream_to_call[stream_sid] = call_sid
        call = self._calls.get(call_sid)
        if call:
            call.stream_sid = stream_sid
        logger.debug(f"Registered stream {stream_sid} for call {call_sid}")

    def end_call(self, call_sid: str) -> Optional[CallState]:
        """Mark call as ended and return final state."""
        call = self._calls.get(call_sid)
        if call:
            call.status = CallStatus.COMPLETED
            call.ended_at = datetime.utcnow()
            logger.info(f"Call ended: {call_sid}, duration: {call.get_duration_seconds():.1f}s")
        return call

    def remove_call(self, call_sid: str):
        """Remove call from active calls (after post-processing)."""
        call = self._calls.pop(call_sid, None)
        if call and call.stream_sid:
            self._stream_to_call.pop(call.stream_sid, None)
        logger.debug(f"Removed call state: {call_sid}")

    def get_active_count(self) -> int:
        """Get count of active calls."""
        return len(self._calls)

    def get_all_active(self) -> List[CallState]:
        """Get all active call states."""
        return list(self._calls.values())


# Global instance
call_manager = CallStateManager()

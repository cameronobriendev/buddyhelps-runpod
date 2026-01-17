"""
Audio format conversion utilities for Twilio Media Streams.

Twilio sends: 8kHz, mulaw encoded, base64
Whisper expects: 16kHz, PCM (16-bit signed)
Kokoro outputs: 24kHz, PCM
Twilio expects back: 8kHz, mulaw encoded, base64
"""
import audioop
import base64
import io
import struct
from typing import Union

import numpy as np


def mulaw_to_pcm16k(mulaw_base64: str) -> bytes:
    """
    Convert Twilio's mulaw audio to PCM for whisper.

    Input: base64 encoded 8kHz mulaw
    Output: 16kHz 16-bit PCM bytes
    """
    # Decode base64
    mulaw_bytes = base64.b64decode(mulaw_base64)

    # Convert mulaw to linear PCM (16-bit)
    # audioop.ulaw2lin returns bytes in native byte order
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)  # 2 = 16-bit samples

    # Resample 8kHz -> 16kHz (whisper expects 16kHz)
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)

    return pcm_16k


def pcm_to_mulaw8k(pcm_bytes: bytes, input_rate: int = 24000) -> str:
    """
    Convert PCM audio back to Twilio's mulaw format.

    Input: PCM bytes at input_rate (default 24kHz from Kokoro)
    Output: base64 encoded 8kHz mulaw
    """
    # Resample to 8kHz
    if input_rate != 8000:
        pcm_8k, _ = audioop.ratecv(pcm_bytes, 2, 1, input_rate, 8000, None)
    else:
        pcm_8k = pcm_bytes

    # Convert PCM to mulaw
    mulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)

    # Encode as base64
    return base64.b64encode(mulaw_bytes).decode('ascii')


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """
    Wrap PCM bytes in a WAV header for processing.

    Useful for passing to whisper which expects WAV format.
    """
    # WAV header for mono 16-bit PCM
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm_bytes)

    # Build WAV header (44 bytes)
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,  # File size - 8
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1 size (PCM)
        1,   # Audio format (1 = PCM)
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size
    )

    return header + pcm_bytes


def chunk_audio_for_streaming(audio_bytes: bytes, chunk_size: int = 640) -> list:
    """
    Split audio into chunks for streaming back to Twilio.

    Twilio expects ~20ms chunks at 8kHz mulaw = 160 bytes
    But we send slightly larger for efficiency.

    Args:
        audio_bytes: Raw mulaw bytes (not base64)
        chunk_size: Bytes per chunk (640 = 40ms at 8kHz mulaw)

    Returns:
        List of base64-encoded chunks
    """
    chunks = []
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i:i + chunk_size]
        chunks.append(base64.b64encode(chunk).decode('ascii'))
    return chunks


class AudioBuffer:
    """
    Buffer for accumulating audio chunks from Twilio.

    Collects chunks until we have enough for processing,
    then returns accumulated audio.
    """

    def __init__(self, min_duration_ms: int = 500):
        """
        Args:
            min_duration_ms: Minimum audio duration before processing.
                            500ms = reasonable for voice activity.
        """
        self.buffer = bytearray()
        self.min_samples = int(16000 * min_duration_ms / 1000)  # At 16kHz

    def add_chunk(self, mulaw_base64: str) -> Union[bytes, None]:
        """
        Add a chunk and return accumulated audio if ready.

        Returns:
            PCM bytes (16kHz) if buffer is full, else None
        """
        # Convert and add to buffer
        pcm = mulaw_to_pcm16k(mulaw_base64)
        self.buffer.extend(pcm)

        # Check if we have enough (2 bytes per sample at 16-bit)
        if len(self.buffer) >= self.min_samples * 2:
            audio = bytes(self.buffer)
            self.buffer.clear()
            return audio

        return None

    def flush(self) -> Union[bytes, None]:
        """Return any remaining audio in buffer."""
        if len(self.buffer) > 0:
            audio = bytes(self.buffer)
            self.buffer.clear()
            return audio
        return None

    def clear(self):
        """Clear the buffer."""
        self.buffer.clear()


def detect_speech_end(pcm_bytes: bytes, threshold: float = 500, min_silence_ms: int = 700) -> bool:
    """
    Simple voice activity detection - check if audio chunk is silence.

    Used to detect when user has stopped speaking.

    Args:
        pcm_bytes: 16-bit PCM audio
        threshold: RMS threshold below which is considered silence
        min_silence_ms: Not used here (tracked by caller)

    Returns:
        True if this chunk is silence
    """
    if len(pcm_bytes) < 2:
        return True

    # Convert to numpy array
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)

    # Calculate RMS
    rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))

    return rms < threshold

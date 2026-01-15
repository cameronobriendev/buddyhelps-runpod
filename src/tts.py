"""
Text-to-Speech using Kokoro-82M

Apache 2.0 licensed, 54 preset voices, 105ms TTFA.
"""
import logging
import time
from typing import Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Global pipeline instance
_pipeline = None

# Available voices (subset of 54 presets)
VOICES = {
    # American Female
    "af_heart": "Friendly, warm female voice (recommended)",
    "af_bella": "Professional female voice",
    "af_sarah": "Casual female voice",
    # American Male
    "am_adam": "Professional male voice",
    "am_michael": "Friendly male voice",
    # British
    "bf_emma": "British female voice",
    "bm_george": "British male voice",
}

DEFAULT_VOICE = "af_heart"


def load_model(lang_code: str = "a"):
    """
    Load Kokoro TTS pipeline.

    Args:
        lang_code: Language code ('a' for American English)
    """
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    logger.info("Loading Kokoro TTS...")

    from kokoro import KPipeline

    _pipeline = KPipeline(lang_code=lang_code)

    logger.info("Kokoro TTS loaded successfully")
    return _pipeline


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
) -> Tuple[np.ndarray, int]:
    """
    Synthesize speech from text.

    Args:
        text: Text to synthesize
        voice: Voice preset name
        speed: Speech speed multiplier

    Returns:
        Tuple of (audio_samples, sample_rate)
    """
    global _pipeline

    if _pipeline is None:
        load_model()

    start = time.perf_counter()

    # Kokoro returns a generator yielding (graphemes, phonemes, audio) tuples
    # Collect all audio chunks and concatenate
    audio_chunks = []
    sample_rate = 24000  # Kokoro default sample rate

    for graphemes, phonemes, audio_chunk in _pipeline(text, voice=voice, speed=speed):
        if audio_chunk is not None:
            # Convert to numpy if needed
            if hasattr(audio_chunk, 'numpy'):
                audio_chunk = audio_chunk.numpy()
            audio_chunks.append(audio_chunk)

    # Concatenate all chunks
    if audio_chunks:
        audio = np.concatenate(audio_chunks)
    else:
        audio = np.array([], dtype=np.float32)

    elapsed = (time.perf_counter() - start) * 1000
    logger.debug(f"TTS completed in {elapsed:.1f}ms for {len(text)} chars")

    return audio, sample_rate


def synthesize_to_bytes(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    format: str = "wav",
) -> bytes:
    """
    Synthesize speech and return as bytes.

    Args:
        text: Text to synthesize
        voice: Voice preset name
        speed: Speech speed multiplier
        format: Output format ('wav')

    Returns:
        Audio as bytes
    """
    import soundfile as sf
    import io

    audio, sample_rate = synthesize(text, voice, speed)

    # Write to buffer
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format=format)
    buffer.seek(0)

    return buffer.read()


def synthesize_to_file(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
):
    """
    Synthesize speech and save to file.

    Args:
        text: Text to synthesize
        output_path: Path to save audio file
        voice: Voice preset name
        speed: Speech speed multiplier
    """
    import soundfile as sf

    audio, sample_rate = synthesize(text, voice, speed)
    sf.write(output_path, audio, sample_rate)
    logger.info(f"Saved TTS output to {output_path}")


def list_voices() -> dict:
    """Return available voice presets."""
    return VOICES.copy()

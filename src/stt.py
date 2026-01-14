"""
Speech-to-Text using NVIDIA Parakeet-TDT

CRITICAL: Requires cuda-python==12.6.2 (NOT 13.x)
13.x breaks CUDA graphs and causes 22x slowdown (800ms vs 34ms)
"""
import logging
import time
from typing import Optional
import numpy as np
import torch

logger = logging.getLogger(__name__)

# Global model instance
_model = None
_is_warmed_up = False


def load_model(model_name: str = "nvidia/parakeet-tdt-0.6b-v2"):
    """Load Parakeet STT model."""
    global _model

    if _model is not None:
        return _model

    logger.info(f"Loading Parakeet model: {model_name}")

    import nemo.collections.asr as nemo_asr

    _model = nemo_asr.models.ASRModel.from_pretrained(model_name)
    _model.cuda().eval()

    logger.info("Parakeet model loaded successfully")
    return _model


def warmup(model=None, num_runs: int = 3):
    """
    Warmup the model by running inference.

    CRITICAL: First inference compiles CUDA graphs (~850ms).
    After warmup, inference runs at 34-38ms.
    """
    global _is_warmed_up

    if model is None:
        model = load_model()

    logger.info(f"Warming up Parakeet ({num_runs} runs)...")

    # Create dummy audio (1 second of silence)
    import soundfile as sf
    import tempfile
    import os

    sample_rate = 16000
    duration = 1.0
    warmup_audio = np.zeros(int(sample_rate * duration), dtype=np.float32)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        warmup_path = f.name
        sf.write(warmup_path, warmup_audio, sample_rate)

    try:
        for i in range(num_runs):
            start = time.perf_counter()
            model.transcribe([warmup_path], batch_size=1)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(f"  Warmup {i+1}/{num_runs}: {elapsed:.1f}ms")
    finally:
        os.unlink(warmup_path)

    _is_warmed_up = True
    logger.info("Parakeet warmup complete - now running at optimal speed")


def transcribe(audio_path: str) -> str:
    """
    Transcribe audio file to text.

    Args:
        audio_path: Path to audio file (WAV, 16kHz mono preferred)

    Returns:
        Transcribed text
    """
    global _model, _is_warmed_up

    if _model is None:
        load_model()

    if not _is_warmed_up:
        logger.warning("Model not warmed up - first inference will be slow")

    start = time.perf_counter()
    result = _model.transcribe([audio_path], batch_size=1)
    elapsed = (time.perf_counter() - start) * 1000

    text = result[0] if result else ""
    logger.debug(f"STT completed in {elapsed:.1f}ms: {text[:50]}...")

    return text


def transcribe_bytes(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    Transcribe audio from bytes.

    Args:
        audio_bytes: Raw audio bytes (WAV format)
        sample_rate: Audio sample rate

    Returns:
        Transcribed text
    """
    import soundfile as sf
    import tempfile
    import os
    import io

    # Write bytes to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name
        f.write(audio_bytes)

    try:
        return transcribe(temp_path)
    finally:
        os.unlink(temp_path)


def transcribe_numpy(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """
    Transcribe audio from numpy array.

    Args:
        audio: Audio samples as numpy array
        sample_rate: Audio sample rate

    Returns:
        Transcribed text
    """
    import soundfile as sf
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name
        sf.write(temp_path, audio, sample_rate)

    try:
        return transcribe(temp_path)
    finally:
        os.unlink(temp_path)

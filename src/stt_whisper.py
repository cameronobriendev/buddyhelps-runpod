"""
Multi-Instance Faster-Whisper STT Pool

Replaces Parakeet with faster-whisper for better concurrency.
Supports 3-4 concurrent STT operations on single GPU.

Licensing: MIT (Whisper) + BSD-3 (faster-whisper) = Commercial OK
"""
import logging
import time
import threading
import tempfile
import os
from typing import Optional, List
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class WhisperInstance:
    """A single faster-whisper model instance with its own lock."""
    model: object  # WhisperModel
    lock: threading.Lock
    index: int
    busy: bool = False
    total_inferences: int = 0
    total_time_ms: float = 0.0


class WhisperPool:
    """
    Pool of faster-whisper instances for concurrent STT.

    Thread-safe: Each instance has its own lock.
    First-available selection minimizes latency.
    """

    def __init__(
        self,
        model_size: str = "base",
        num_instances: int = 4,
        device: str = "cuda",
        compute_type: str = "float16",
        download_root: Optional[str] = None,
    ):
        self.model_size = model_size
        self.num_instances = num_instances
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root

        self.instances: List[WhisperInstance] = []
        self._pool_lock = threading.Lock()  # For instance selection only
        self._is_loaded = False
        self._is_warmed_up = False

    def load(self):
        """Load all model instances."""
        if self._is_loaded:
            return

        from faster_whisper import WhisperModel

        logger.info(f"Loading {self.num_instances}x faster-whisper ({self.model_size}, {self.compute_type})")

        for i in range(self.num_instances):
            start = time.perf_counter()
            model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
            elapsed = (time.perf_counter() - start) * 1000

            instance = WhisperInstance(
                model=model,
                lock=threading.Lock(),
                index=i,
            )
            self.instances.append(instance)
            logger.info(f"  Instance {i+1}/{self.num_instances} loaded in {elapsed:.0f}ms")

        self._is_loaded = True
        logger.info(f"Whisper pool ready: {self.num_instances} instances")

    def warmup(self, num_runs: int = 2):
        """
        Warmup all instances by running inference.
        CTranslate2 compiles kernels on first run.
        """
        if not self._is_loaded:
            self.load()

        if self._is_warmed_up:
            return

        logger.info(f"Warming up Whisper pool ({num_runs} runs per instance)...")

        # Create dummy audio (1 second of silence at 16kHz)
        import soundfile as sf
        sample_rate = 16000
        warmup_audio = np.zeros(sample_rate, dtype=np.float32)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            warmup_path = f.name
            sf.write(warmup_path, warmup_audio, sample_rate)

        try:
            for instance in self.instances:
                for run in range(num_runs):
                    start = time.perf_counter()
                    segments, _ = instance.model.transcribe(
                        warmup_path,
                        beam_size=1,
                        vad_filter=False,
                    )
                    list(segments)  # Consume generator
                    elapsed = (time.perf_counter() - start) * 1000
                    logger.info(f"  Instance {instance.index} warmup {run+1}: {elapsed:.1f}ms")
        finally:
            os.unlink(warmup_path)

        self._is_warmed_up = True
        logger.info("Whisper pool warmup complete")

    def _get_available_instance(self, timeout: float = 5.0) -> Optional[WhisperInstance]:
        """
        Get first available instance (non-blocking if possible).
        Falls back to waiting on first instance if all busy.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            # Try to acquire any unlocked instance
            with self._pool_lock:
                for instance in self.instances:
                    if instance.lock.acquire(blocking=False):
                        instance.busy = True
                        return instance

            # All busy - sleep briefly and retry
            time.sleep(0.005)  # 5ms

        # Timeout - wait on first instance (guaranteed to eventually unlock)
        logger.warning("All Whisper instances busy, waiting...")
        instance = self.instances[0]
        instance.lock.acquire(blocking=True)
        instance.busy = True
        return instance

    def _release_instance(self, instance: WhisperInstance):
        """Release instance back to pool."""
        instance.busy = False
        instance.lock.release()

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        beam_size: int = 1,
        vad_filter: bool = True,
        vad_parameters: Optional[dict] = None,
    ) -> str:
        """
        Transcribe audio file to text.
        Automatically selects an available instance.
        """
        if not self._is_loaded:
            self.load()

        instance = self._get_available_instance()
        if instance is None:
            raise RuntimeError("No Whisper instance available")

        try:
            start = time.perf_counter()

            segments, info = instance.model.transcribe(
                audio_path,
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                vad_parameters=vad_parameters or {"min_silence_duration_ms": 250},
            )

            # Collect all segment text
            text = " ".join(segment.text.strip() for segment in segments)

            elapsed = (time.perf_counter() - start) * 1000
            instance.total_inferences += 1
            instance.total_time_ms += elapsed

            logger.debug(f"STT[{instance.index}] completed in {elapsed:.1f}ms: {text[:50]}...")
            return text

        finally:
            self._release_instance(instance)

    def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe audio from bytes (WAV format).
        Writes to temp file (faster-whisper requires file path).
        """
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            f.write(audio_bytes)

        try:
            return self.transcribe(temp_path)
        finally:
            os.unlink(temp_path)

    def transcribe_numpy(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio from numpy array."""
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            sf.write(temp_path, audio, sample_rate)

        try:
            return self.transcribe(temp_path)
        finally:
            os.unlink(temp_path)

    def get_stats(self) -> dict:
        """Get pool statistics."""
        return {
            "model_size": self.model_size,
            "num_instances": self.num_instances,
            "compute_type": self.compute_type,
            "is_loaded": self._is_loaded,
            "is_warmed_up": self._is_warmed_up,
            "instances": [
                {
                    "index": inst.index,
                    "busy": inst.busy,
                    "total_inferences": inst.total_inferences,
                    "avg_latency_ms": round(
                        inst.total_time_ms / inst.total_inferences, 1
                    ) if inst.total_inferences > 0 else 0,
                }
                for inst in self.instances
            ],
        }


# ============ Audio Preprocessing for Phone Audio ============

def preprocess_phone_audio(
    audio_bytes: bytes,
    input_format: str = "mulaw",
    input_sample_rate: int = 8000,
    output_sample_rate: int = 16000,
) -> bytes:
    """
    Preprocess phone audio for Whisper.

    Phone audio is typically:
    - 8kHz sample rate
    - mulaw or alaw encoded
    - Mono

    Whisper expects:
    - 16kHz sample rate
    - Linear PCM
    - Mono
    """
    import audioop
    from scipy import signal
    import soundfile as sf
    import io

    # Step 1: Decode mulaw/alaw to linear PCM
    if input_format == "mulaw":
        linear_bytes = audioop.ulaw2lin(audio_bytes, 2)  # 2 = 16-bit
    elif input_format == "alaw":
        linear_bytes = audioop.alaw2lin(audio_bytes, 2)
    elif input_format == "pcm16":
        linear_bytes = audio_bytes
    else:
        raise ValueError(f"Unknown format: {input_format}")

    # Step 2: Convert bytes to numpy
    audio_int16 = np.frombuffer(linear_bytes, dtype=np.int16)
    audio_float = audio_int16.astype(np.float32) / 32768.0

    # Step 3: Resample from 8kHz to 16kHz
    if input_sample_rate != output_sample_rate:
        num_samples = int(len(audio_float) * output_sample_rate / input_sample_rate)
        audio_resampled = signal.resample(audio_float, num_samples)
    else:
        audio_resampled = audio_float

    # Step 4: Write to WAV bytes
    buffer = io.BytesIO()
    sf.write(buffer, audio_resampled, output_sample_rate, format='WAV')
    buffer.seek(0)
    return buffer.read()


# ============ Global Pool Instance ============

_pool: Optional[WhisperPool] = None


def load_model(
    model_size: str = "base",
    num_instances: int = 4,
    device: str = "cuda",
    compute_type: str = "float16",
) -> WhisperPool:
    """Load the Whisper pool (singleton)."""
    global _pool

    if _pool is not None:
        return _pool

    _pool = WhisperPool(
        model_size=model_size,
        num_instances=num_instances,
        device=device,
        compute_type=compute_type,
    )
    _pool.load()
    return _pool


def warmup(num_runs: int = 2):
    """Warmup the pool."""
    global _pool
    if _pool is None:
        load_model()
    _pool.warmup(num_runs=num_runs)


def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text."""
    global _pool
    if _pool is None:
        load_model()
    return _pool.transcribe(audio_path)


def transcribe_bytes(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """Transcribe audio from bytes."""
    global _pool
    if _pool is None:
        load_model()
    return _pool.transcribe_bytes(audio_bytes, sample_rate)


def transcribe_numpy(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribe audio from numpy array."""
    global _pool
    if _pool is None:
        load_model()
    return _pool.transcribe_numpy(audio, sample_rate)


def transcribe_phone_audio(
    audio_bytes: bytes,
    input_format: str = "mulaw",
    input_sample_rate: int = 8000,
) -> str:
    """
    Transcribe phone audio (8kHz mulaw).
    Handles preprocessing automatically.
    """
    preprocessed = preprocess_phone_audio(
        audio_bytes,
        input_format=input_format,
        input_sample_rate=input_sample_rate,
    )
    return transcribe_bytes(preprocessed)


def get_stats() -> dict:
    """Get pool statistics."""
    global _pool
    if _pool is None:
        return {"status": "not_loaded"}
    return _pool.get_stats()

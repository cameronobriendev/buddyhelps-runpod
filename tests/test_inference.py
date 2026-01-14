"""
Basic inference tests.

Run with: pytest tests/
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSTT:
    """Test Speech-to-Text module."""

    def test_model_loads(self):
        """Test that Parakeet model loads."""
        from src import stt
        model = stt.load_model()
        assert model is not None

    def test_warmup_completes(self):
        """Test that warmup runs without error."""
        from src import stt
        stt.load_model()
        stt.warmup(num_runs=1)
        assert stt._is_warmed_up


class TestLLM:
    """Test LLM module."""

    def test_model_loads(self):
        """Test that Qwen model loads."""
        from src import llm
        model = llm.load_model()
        assert model is not None

    def test_generation(self):
        """Test basic generation."""
        from src import llm
        llm.load_model()

        response = llm.generate_simple(
            "Hello, I have a leaky faucet.",
            business_name="Test Plumbing",
            owner_name="Mike",
        )

        assert response is not None
        assert len(response) > 0


class TestTTS:
    """Test Text-to-Speech module."""

    def test_model_loads(self):
        """Test that Kokoro model loads."""
        from src import tts
        pipeline = tts.load_model()
        assert pipeline is not None

    def test_synthesis(self):
        """Test basic synthesis."""
        from src import tts
        tts.load_model()

        audio, sr = tts.synthesize("Hello, this is a test.")

        assert audio is not None
        assert len(audio) > 0
        assert sr > 0

    def test_voices(self):
        """Test voice listing."""
        from src import tts
        voices = tts.list_voices()

        assert "af_heart" in voices
        assert "am_adam" in voices


class TestPipeline:
    """Test full pipeline."""

    def test_all_models_load(self):
        """Test that all models can be loaded together."""
        from src import stt, llm, tts

        stt.load_model()
        llm.load_model()
        tts.load_model()

        assert stt._model is not None
        assert llm._llm is not None
        assert tts._pipeline is not None

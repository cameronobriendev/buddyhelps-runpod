#!/usr/bin/env python3
"""
Model Warmup Script

CRITICAL: Run this before accepting calls!

First inference after model load takes ~850ms (CUDA graph compilation).
After warmup, Parakeet runs at 34-38ms.
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("BuddyHelps Model Warmup")
    logger.info("=" * 60)

    total_start = time.perf_counter()

    # Warmup STT (most critical - CUDA graphs)
    logger.info("\n[1/3] Loading and warming up STT (Parakeet)...")
    from src import stt
    stt.load_model()
    stt.warmup(num_runs=3)

    # Load LLM
    logger.info("\n[2/3] Loading LLM (Qwen2.5-0.5B)...")
    from src import llm
    llm.load_model()

    # Test LLM
    logger.info("Testing LLM...")
    test_response = llm.generate_simple(
        "Hello, I have a plumbing problem.",
        business_name="Test Plumbing",
        owner_name="Mike",
    )
    logger.info(f"LLM test response: {test_response[:100]}...")

    # Load TTS
    logger.info("\n[3/3] Loading TTS (Kokoro)...")
    from src import tts
    tts.load_model()

    # Test TTS
    logger.info("Testing TTS...")
    audio, sr = tts.synthesize("Hello, this is Benny with Test Plumbing.")
    logger.info(f"TTS test: Generated {len(audio)} samples at {sr}Hz")

    total_elapsed = time.perf_counter() - total_start

    logger.info("\n" + "=" * 60)
    logger.info(f"Warmup complete in {total_elapsed:.1f}s")
    logger.info("All models loaded and ready for inference!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

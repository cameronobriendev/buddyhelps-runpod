"""
LLM Inference using Qwen2.5-0.5B-Instruct

NOTE: Using FP16, NOT INT4. Sub-1B models lose 10-20% quality at INT4.
"""
import logging
import time
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Global model instance
_llm = None

# Load conversation prompt template
PROMPT_TEMPLATE = None


def load_prompt_template():
    """Load the conversation prompt template."""
    global PROMPT_TEMPLATE

    if PROMPT_TEMPLATE is not None:
        return PROMPT_TEMPLATE

    prompt_path = Path(__file__).parent.parent / "prompts" / "conversation.txt"
    if prompt_path.exists():
        PROMPT_TEMPLATE = prompt_path.read_text()
    else:
        # Default template
        PROMPT_TEMPLATE = """You are Benny, answering phones for {business_name}, a plumbing company.

WHO YOU ARE:
- Friendly, warm, genuinely helpful
- You work with {owner_name} and know how they operate
- You're part of the team, not a robot or answering service

YOUR GOAL:
Have a real conversation. Listen. Respond naturally. Make the caller feel like they reached someone who cares. {owner_name} will call them back.

HOW YOU TALK:
- Respond to what they actually say
- If they sound stressed, acknowledge it
- Keep responses conversational, not scripted
- Never give quotes or prices - that's {owner_name}'s job

Keep responses brief (1-3 sentences). This is a phone conversation."""

    return PROMPT_TEMPLATE


def load_model(model_name: str = "Qwen/Qwen2.5-0.5B-Instruct"):
    """Load Qwen LLM with vLLM."""
    global _llm

    if _llm is not None:
        return _llm

    logger.info(f"Loading LLM: {model_name}")

    from vllm import LLM

    _llm = LLM(
        model=model_name,
        dtype="float16",  # NOT int4 - quality loss too high for sub-1B
        gpu_memory_utilization=0.3,  # Leave room for STT and TTS
        max_model_len=2048,
    )

    logger.info("LLM loaded successfully")
    return _llm


def generate(
    messages: List[Dict[str, str]],
    business_name: str = "the plumbing company",
    owner_name: str = "the owner",
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """
    Generate a response from the LLM.

    Args:
        messages: Conversation history [{"role": "user/assistant", "content": "..."}]
        business_name: Name of the plumbing business
        owner_name: Name of the business owner
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        Generated response text
    """
    global _llm

    if _llm is None:
        load_model()

    from vllm import SamplingParams

    # Build the system prompt
    template = load_prompt_template()
    system_prompt = template.format(
        business_name=business_name,
        owner_name=owner_name,
    )

    # Format messages for Qwen
    formatted_messages = [{"role": "system", "content": system_prompt}]
    formatted_messages.extend(messages)

    # Apply chat template
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
    prompt = tokenizer.apply_chat_template(
        formatted_messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    # Generate
    sampling_params = SamplingParams(
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=0.9,
        stop=["<|im_end|>", "<|endoftext|>"],
    )

    start = time.perf_counter()
    outputs = _llm.generate([prompt], sampling_params)
    elapsed = (time.perf_counter() - start) * 1000

    response = outputs[0].outputs[0].text.strip()
    logger.debug(f"LLM completed in {elapsed:.1f}ms: {response[:50]}...")

    return response


def generate_simple(user_input: str, **kwargs) -> str:
    """
    Simple single-turn generation.

    Args:
        user_input: User's message
        **kwargs: Passed to generate()

    Returns:
        Generated response
    """
    messages = [{"role": "user", "content": user_input}]
    return generate(messages, **kwargs)

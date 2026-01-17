"""
LLM Inference using Qwen2.5-0.5B-Instruct with HuggingFace Transformers

Switched from vLLM to Transformers for stability. vLLM 0.13.0's v1 engine
spawns child processes that fail CUDA init on RunPod. For a 0.5B model,
Transformers is plenty fast (~50-80ms) and runs single-process.
"""
import logging
import time
from typing import List, Dict, Optional
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)

# Global model instances
_model = None
_tokenizer = None

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
        PROMPT_TEMPLATE = """You are {greeting_name}, answering phones for {business_name}, a plumbing company.

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
    """Load Qwen LLM with HuggingFace Transformers."""
    global _model, _tokenizer

    if _model is not None:
        return _model

    logger.info(f"Loading LLM: {model_name}")

    # Load tokenizer
    _tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Load model in FP16 for speed
    _model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map="cuda",
    )
    _model.eval()

    # Warmup inference
    logger.info("Warming up LLM...")
    warmup_messages = [{"role": "user", "content": "Hello"}]
    _ = generate(warmup_messages, max_tokens=10)

    logger.info("LLM loaded successfully")
    return _model


def generate(
    messages: List[Dict[str, str]],
    business_name: str = "the plumbing company",
    owner_name: str = "the owner",
    greeting_name: str = "Benny",
    system_prompt: Optional[str] = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """
    Generate a response from the LLM.

    Args:
        messages: Conversation history [{"role": "user/assistant", "content": "..."}]
        business_name: Name of the plumbing business
        owner_name: Name of the business owner
        greeting_name: Name the AI introduces itself as
        system_prompt: Custom system prompt (overrides template if provided)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        Generated response text
    """
    global _model, _tokenizer

    if _model is None:
        load_model()

    # Use custom system prompt if provided, otherwise use template
    if system_prompt:
        # Format any placeholders in the custom prompt
        system_prompt = system_prompt.format(
            business_name=business_name,
            owner_name=owner_name,
            greeting_name=greeting_name,
        )
    else:
        template = load_prompt_template()
        system_prompt = template.format(
            business_name=business_name,
            owner_name=owner_name,
            greeting_name=greeting_name,
        )

    # Format messages for Qwen
    formatted_messages = [{"role": "system", "content": system_prompt}]
    formatted_messages.extend(messages)

    # Apply chat template
    prompt = _tokenizer.apply_chat_template(
        formatted_messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    # Tokenize
    inputs = _tokenizer(prompt, return_tensors="pt").to(_model.device)

    # Generate
    start = time.perf_counter()
    with torch.no_grad():
        outputs = _model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
            do_sample=True,
            pad_token_id=_tokenizer.pad_token_id or _tokenizer.eos_token_id,
        )
    elapsed = (time.perf_counter() - start) * 1000

    # Decode only the new tokens
    response = _tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    ).strip()

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

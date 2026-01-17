"""
STT Post-Processing: Industry-specific keyword corrections.

Phone audio quality causes STT to mishear domain-specific words.
This module applies corrections before sending to LLM.

Performance: Sub-millisecond (just regex).
"""
import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def apply_corrections(text: str, corrections: Dict[str, str]) -> str:
    """
    Apply industry-specific corrections to STT output.

    Args:
        text: Raw STT transcript
        corrections: Dict of {wrong_word: correct_word}

    Returns:
        Corrected text
    """
    if not corrections or not text:
        return text

    corrected = text
    changes = []

    for wrong, right in corrections.items():
        # Case-insensitive word boundary replacement
        pattern = re.compile(rf'\b{re.escape(wrong)}\b', re.IGNORECASE)

        # Check if there's a match before replacing
        if pattern.search(corrected):
            corrected = pattern.sub(right, corrected)
            changes.append(f'"{wrong}" -> "{right}"')

    if changes:
        logger.info(f"STT corrections applied: {', '.join(changes)}")
        logger.debug(f"Original: {text}")
        logger.debug(f"Corrected: {corrected}")

    return corrected

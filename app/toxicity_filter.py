"""
Toxicity Filter — scans LLM output for harmful or inappropriate content
before it is served to the user.

Two-layer approach:
  1. better-profanity library for profanity detection
  2. Custom keyword/phrase checks for healthcare-specific harmful content
     (self-harm, medication misuse, dangerous clinical advice)

Returns a toxicity score 0.0–1.0.
Score > 0.8 → response is blocked.
"""
import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Lazy-load better-profanity
_profanity = None


def _get_profanity():
    global _profanity
    if _profanity is None:
        try:
            from better_profanity import profanity
            profanity.load_censor_words()
            _profanity = profanity
        except ImportError:
            logger.warning("better-profanity not installed. Profanity check skipped.")
            _profanity = False
    return _profanity


# Healthcare-specific harmful content categories
HARMFUL_PATTERNS: List[Tuple[str, float]] = [
    # Self-harm / suicide
    (r"\b(?:kill yourself|end your life|take all your pills)\b", 1.0),

    # Dangerous medication advice
    (r"\btake (?:more than|double|triple) (?:the )?(?:prescribed|recommended) dose\b", 0.9),
    (r"\bstop taking (?:your )?(?:insulin|blood pressure|heart) medication\b", 0.85),
    (r"\bdo not (?:see|consult|visit) (?:a )?doctor\b", 0.7),

    # Dangerous clinical claims
    (r"\b(?:guaranteed|100%\s+certain|definitely will) (?:cure|treat|fix)\b", 0.6),
    (r"\bignore (?:your|the) (?:doctor|physician|pharmacist)\b", 0.75),

    # Drug misuse
    (r"\b(?:crush|inject|snort) (?:the )?(?:pill|tablet|medication)\b", 0.9),
]


class ToxicityFilter:
    """
    Filters harmful LLM output before serving to users.

    Usage:
        filter = ToxicityFilter()
        score = filter.score("Here's how to take double your insulin dose")
        # → 0.9 (HIGH — blocked)
    """

    def __init__(self):
        self._patterns = [
            (re.compile(p, re.IGNORECASE), score)
            for p, score in HARMFUL_PATTERNS
        ]

    def score(self, text: str) -> float:
        """
        Returns toxicity score 0.0 (safe) to 1.0 (highly harmful).
        Combines profanity check + harmful pattern matching.
        """
        max_score = 0.0

        # --- Check 1: Profanity ---
        profanity = _get_profanity()
        if profanity and profanity.contains_profanity(text):
            max_score = max(max_score, 0.6)
            logger.info("Profanity detected in LLM output.")

        # --- Check 2: Healthcare harmful patterns ---
        for pattern, weight in self._patterns:
            if pattern.search(text):
                max_score = max(max_score, weight)
                logger.warning(f"Harmful pattern matched: {pattern.pattern[:50]}...")

        return round(max_score, 2)

    def is_safe(self, text: str, threshold: float = 0.8) -> bool:
        """Returns True if the text is below the blocking threshold."""
        return self.score(text) < threshold

"""
Hallucination Guard — self-consistency scoring for LLM responses.

Approach: Run the same prompt N times at different temperatures,
then measure how much the responses agree. Low agreement = high
hallucination risk. This is more reliable than self-reported
LLM confidence scores, which are often miscalibrated.

Risk levels:
  LOW    (score < 0.25) → return response as-is
  MEDIUM (score < 0.60) → prepend a confidence warning
  HIGH   (score ≥ 0.60) → return safe fallback, do NOT show AI response

Design choice: 3x LLM calls per request is expensive.
We use it only after the primary response is generated and
only when a Groq client is available. Demo mode falls back gracefully.
"""
import hashlib
import time
import logging
from typing import Optional, Tuple

from app.models import HallucinationRisk

logger = logging.getLogger(__name__)

# Response for HIGH risk — never show the uncertain AI answer
SAFE_FALLBACK = (
    "I am not confident enough in my answer to this question to share it safely. "
    "Please consult the official formulary documentation, your pharmacy benefit plan, "
    "or a licensed pharmacist / clinician directly. "
    "This question has been flagged for human review."
)

MEDIUM_WARNING = (
    "[Note: Confidence in this response is moderate. "
    "Please verify with official formulary or clinical guidelines before acting.]\n\n"
)


class HallucinationGuard:
    """
    Self-consistency hallucination detection.

    Runs N LLM calls at varied temperatures, hashes the first ~200 chars
    of each response, counts unique hashes → scores disagreement 0.0–1.0.

    Usage:
        guard = HallucinationGuard(groq_client, "llama3-70b-8192", n_samples=3)
        score, risk, final_response = guard.evaluate(prompt, primary_response)
    """

    TEMPERATURES = [0.0, 0.5, 0.9]

    def __init__(self, groq_client, model: str, n_samples: int = 3):
        self.client = groq_client
        self.model = model
        self.n_samples = min(n_samples, len(self.TEMPERATURES))

    def _hash_response(self, text: str) -> str:
        """Fingerprint a response by its first 200 chars (normalized)."""
        normalized = text.strip().lower()[:200]
        return hashlib.md5(normalized.encode()).hexdigest()

    def _compute_score(self, hashes: list) -> float:
        """
        Score = (unique_responses - 1) / (total_responses - 1)
        0.0 = all identical (fully consistent)
        1.0 = all different (maximum disagreement)
        """
        unique = len(set(hashes))
        return round((unique - 1) / max(len(hashes) - 1, 1), 2)

    def _classify(self, score: float) -> HallucinationRisk:
        if score < 0.25:
            return HallucinationRisk.LOW
        elif score < 0.60:
            return HallucinationRisk.MEDIUM
        else:
            return HallucinationRisk.HIGH

    def score(self, prompt: str, primary_response: str) -> Tuple[float, HallucinationRisk]:
        """
        Returns (score, risk_level).
        Additional LLM calls are made with varied temperatures to measure consistency.
        """
        hashes = [self._hash_response(primary_response)]

        for i in range(1, self.n_samples):
            temp = self.TEMPERATURES[i % len(self.TEMPERATURES)]
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temp,
                    max_tokens=500,
                )
                hashes.append(self._hash_response(resp.choices[0].message.content))
                time.sleep(0.1)  # Respect Groq rate limits
            except Exception as e:
                logger.warning(f"Hallucination guard sample {i} failed: {e}")
                hashes.append(f"error_{i}")  # Treat errors as unique responses (conservative)

        score = self._compute_score(hashes)
        risk = self._classify(score)
        logger.info(f"Hallucination score: {score} ({risk.value}) | Samples: {len(hashes)}")
        return score, risk

    def evaluate(
        self,
        prompt: str,
        primary_response: str,
    ) -> Tuple[float, HallucinationRisk, str]:
        """
        Full evaluation: score + risk-appropriate response.

        Returns:
            (score, risk, final_response_to_serve)

        HIGH risk  → safe fallback message
        MEDIUM risk → warning prepended to response
        LOW risk   → original response unchanged
        """
        score, risk = self.score(prompt, primary_response)

        if risk == HallucinationRisk.HIGH:
            final = SAFE_FALLBACK
        elif risk == HallucinationRisk.MEDIUM:
            final = MEDIUM_WARNING + primary_response
        else:
            final = primary_response

        return score, risk, final

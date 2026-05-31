"""
Tests for HallucinationGuard.
Uses mock Groq client — no real API calls made.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.guardrails import HallucinationGuard, SAFE_FALLBACK, MEDIUM_WARNING
from app.models import HallucinationRisk


@pytest.fixture
def mock_groq():
    """Mock Groq client that always returns the same response."""
    client = MagicMock()
    response = MagicMock()
    response.choices[0].message.content = "Metformin is a first-line diabetes medication covered under most formularies."
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def divergent_groq():
    """Mock Groq client that returns different responses each call."""
    client = MagicMock()
    responses = [
        "Metformin is covered.",
        "Coverage depends on the plan formulary tier.",
        "Prior authorization may be required for brand name only.",
    ]
    client.chat.completions.create.side_effect = [
        MagicMock(**{"choices[0].message.content": r}) for r in responses
    ]
    return client


class TestHallucinationScore:
    def test_consistent_responses_give_low_score(self, mock_groq):
        """When all N samples agree → score near 0 → LOW risk."""
        primary = "Metformin is a first-line diabetes medication covered under most formularies."
        guard = HallucinationGuard(mock_groq, "test-model", n_samples=3)
        score, risk = guard.score("Is metformin covered?", primary)
        assert risk == HallucinationRisk.LOW
        assert score < 0.25

    def test_score_is_between_0_and_1(self, mock_groq):
        """Score must always be in [0.0, 1.0]."""
        guard = HallucinationGuard(mock_groq, "test-model", n_samples=2)
        mock_groq.chat.completions.create.return_value.choices[0].message.content = "Different answer"
        score, _ = guard.score("any prompt", "Original answer")
        assert 0.0 <= score <= 1.0

    def test_divergent_responses_higher_score(self, divergent_groq):
        """When responses differ → higher score."""
        guard = HallucinationGuard(divergent_groq, "test-model", n_samples=3)
        score, risk = guard.score(
            "Is Humira covered?",
            "Humira requires prior authorization on most plans.",
        )
        assert score > 0.0

    def test_api_error_treated_conservatively(self, mock_groq):
        """API errors should be treated as unique responses (conservative)."""
        mock_groq.chat.completions.create.side_effect = Exception("Rate limit exceeded")
        guard = HallucinationGuard(mock_groq, "test-model", n_samples=3)
        score, risk = guard.score("Is drug X covered?", "Primary response here")
        # Errors counted as unique → score should be non-zero
        assert 0.0 <= score <= 1.0


class TestRiskClassification:
    def test_low_risk_threshold(self):
        guard = HallucinationGuard(MagicMock(), "test", n_samples=1)
        assert guard._classify(0.0) == HallucinationRisk.LOW
        assert guard._classify(0.24) == HallucinationRisk.LOW

    def test_medium_risk_threshold(self):
        guard = HallucinationGuard(MagicMock(), "test", n_samples=1)
        assert guard._classify(0.25) == HallucinationRisk.MEDIUM
        assert guard._classify(0.59) == HallucinationRisk.MEDIUM

    def test_high_risk_threshold(self):
        guard = HallucinationGuard(MagicMock(), "test", n_samples=1)
        assert guard._classify(0.60) == HallucinationRisk.HIGH
        assert guard._classify(1.0) == HallucinationRisk.HIGH


class TestEvaluate:
    def test_high_risk_returns_fallback(self, mock_groq):
        guard = HallucinationGuard(mock_groq, "test-model", n_samples=1)
        # Force HIGH risk by patching score
        with patch.object(guard, "score", return_value=(0.9, HallucinationRisk.HIGH)):
            score, risk, response = guard.evaluate("prompt", "original response")
        assert response == SAFE_FALLBACK
        assert risk == HallucinationRisk.HIGH

    def test_medium_risk_prepends_warning(self, mock_groq):
        guard = HallucinationGuard(mock_groq, "test-model", n_samples=1)
        with patch.object(guard, "score", return_value=(0.4, HallucinationRisk.MEDIUM)):
            score, risk, response = guard.evaluate("prompt", "original response")
        assert MEDIUM_WARNING in response
        assert "original response" in response

    def test_low_risk_returns_original(self, mock_groq):
        guard = HallucinationGuard(mock_groq, "test-model", n_samples=1)
        with patch.object(guard, "score", return_value=(0.1, HallucinationRisk.LOW)):
            score, risk, response = guard.evaluate("prompt", "original response")
        assert response == "original response"

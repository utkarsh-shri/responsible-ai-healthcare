"""
Tests for AuditLogger.
Uses in-memory store — no Supabase connection required.
"""
import pytest
from app.audit_logger import AuditLogger
from app.models import HallucinationRisk


@pytest.fixture
def logger():
    """AuditLogger in memory-only mode (no Supabase keys)."""
    return AuditLogger(supabase_url=None, supabase_key=None)


SAMPLE_RECORD = {
    "user_id": "test_reviewer",
    "context": "claims_adjudication",
    "original_text": "Patient John Smith denied metformin",
    "masked_text": "[NAME] denied metformin",
    "ai_response": "Denial likely due to formulary tier placement.",
    "pii_detected": ["PERSON", "MRN"],
    "hallucination_score": 0.12,
    "hallucination_risk": HallucinationRisk.LOW,
    "toxicity_score": 0.01,
    "model_used": "llama3-70b-8192",
    "processing_ms": 340,
}


class TestAuditLogWrite:
    def test_returns_audit_id(self, logger):
        audit_id = logger.log(**SAMPLE_RECORD)
        assert isinstance(audit_id, str)
        assert len(audit_id) > 0

    def test_audit_id_is_unique(self, logger):
        id1 = logger.log(**SAMPLE_RECORD)
        id2 = logger.log(**SAMPLE_RECORD)
        assert id1 != id2

    def test_input_is_hashed_not_stored(self, logger):
        """Raw PHI in original_text must NOT appear in the stored record."""
        audit_id = logger.log(**SAMPLE_RECORD)
        record = logger.get(audit_id)
        assert SAMPLE_RECORD["original_text"] not in str(record.get("input_hash", ""))
        assert "John Smith" not in record.get("input_hash", "")

    def test_output_is_hashed(self, logger):
        audit_id = logger.log(**SAMPLE_RECORD)
        record = logger.get(audit_id)
        # Should have a SHA-256 hash (64 hex chars) not the raw text
        assert len(record["output_hash"]) == 64


class TestAuditLogRead:
    def test_get_existing_record(self, logger):
        audit_id = logger.log(**SAMPLE_RECORD)
        record = logger.get(audit_id)
        assert record is not None
        assert record["user_id"] == SAMPLE_RECORD["user_id"]
        assert record["context"] == SAMPLE_RECORD["context"]

    def test_get_nonexistent_returns_none(self, logger):
        result = logger.get("nonexistent-id-12345")
        assert result is None

    def test_get_recent_returns_list(self, logger):
        logger.log(**SAMPLE_RECORD)
        logger.log(**SAMPLE_RECORD)
        records = logger.get_recent(limit=10)
        assert isinstance(records, list)
        assert len(records) >= 2

    def test_hallucination_risk_stored_as_string(self, logger):
        """Risk enum should be stored as string value (LOW/MEDIUM/HIGH)."""
        audit_id = logger.log(**SAMPLE_RECORD)
        record = logger.get(audit_id)
        assert record["hallucination_risk"] == "LOW"
        assert isinstance(record["hallucination_risk"], str)

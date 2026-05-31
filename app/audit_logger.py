"""
Audit Logger — immutable, structured audit trail for every AI decision.

Maps to HIPAA Security Rule §164.312(b): Audit Controls requirement.
Every AI decision is recorded with:
  - SHA-256 hash of input (never the raw PHI)
  - SHA-256 hash of output
  - PII types detected (types only, not values)
  - Hallucination score and risk level
  - Toxicity score
  - Model used and latency

Design: Supabase table has INSERT + SELECT RLS policies but NO UPDATE
or DELETE policies → tamper-evident by construction.

When Supabase is not configured (e.g., local dev without keys),
falls back to in-memory store so the pipeline still works end-to-end.
"""
import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List

from app.models import HallucinationRisk

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Writes one immutable record per AI decision.

    Usage:
        logger = AuditLogger(supabase_url, supabase_service_key)
        audit_id = logger.log(user_id="u1", context="formulary", ...)
        record = logger.get(audit_id)
    """

    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self._client = None
        self._memory_store: dict = {}  # Fallback when Supabase is unavailable

        if supabase_url and supabase_key and "supabase.co" in supabase_url:
            try:
                from supabase import create_client
                self._client = create_client(supabase_url, supabase_key)
                logger.info("AuditLogger connected to Supabase.")
            except Exception as e:
                logger.warning(f"Supabase connection failed ({e}). Using in-memory store.")
        else:
            logger.info("Supabase not configured. AuditLogger using in-memory store.")

    def _sha256(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def log(
        self,
        user_id: str,
        context: str,
        original_text: str,
        masked_text: str,
        ai_response: str,
        pii_detected: List[str],
        hallucination_score: float,
        hallucination_risk: HallucinationRisk,
        toxicity_score: float,
        model_used: str,
        processing_ms: int,
    ) -> str:
        """
        Write one audit record. Returns the audit_id (UUID string).
        Input/output are hashed — original PHI is never stored.
        """
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "id": audit_id,
            "created_at": now,
            "user_id": user_id,
            "context": context,
            "input_hash": self._sha256(original_text),
            "output_hash": self._sha256(ai_response),
            "masked_text": masked_text,
            "ai_response": ai_response,
            "pii_detected": pii_detected,
            "hallucination_score": hallucination_score,
            "hallucination_risk": hallucination_risk.value,
            "toxicity_score": toxicity_score,
            "model_used": model_used,
            "processing_ms": processing_ms,
        }

        if self._client:
            try:
                # Insert without the 'id' key — let Supabase generate UUID
                supabase_record = {k: v for k, v in record.items() if k != "id"}
                result = self._client.table("audit_logs").insert(supabase_record).execute()
                returned_id = result.data[0]["id"]
                self._memory_store[returned_id] = result.data[0]  # Cache locally
                logger.info(f"Audit log written to Supabase: {returned_id}")
                return returned_id
            except Exception as e:
                logger.error(f"Supabase write failed ({e}). Falling back to memory store.")

        # In-memory fallback
        self._memory_store[audit_id] = record
        logger.info(f"Audit log written to memory store: {audit_id}")
        return audit_id

    def get(self, audit_id: str) -> Optional[dict]:
        """Retrieve an audit record by ID."""
        # Check local cache first
        if audit_id in self._memory_store:
            return self._memory_store[audit_id]

        if self._client:
            try:
                result = (
                    self._client.table("audit_logs")
                    .select("*")
                    .eq("id", audit_id)
                    .execute()
                )
                if result.data:
                    self._memory_store[audit_id] = result.data[0]
                    return result.data[0]
            except Exception as e:
                logger.error(f"Supabase read failed: {e}")

        return None

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Get most recent audit log entries."""
        if self._client:
            try:
                result = (
                    self._client.table("audit_logs")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return result.data or []
            except Exception as e:
                logger.error(f"Supabase query failed: {e}")

        # Return from memory store sorted by created_at
        records = list(self._memory_store.values())
        records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return records[:limit]

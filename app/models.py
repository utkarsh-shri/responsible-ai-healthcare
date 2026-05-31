"""
Pydantic models for request/response validation.
All API boundaries are validated here before any processing.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from enum import Enum
import re


class HallucinationRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


ALLOWED_CONTEXTS = {
    "claims_adjudication",
    "prior_authorization",
    "formulary",
    "general",
    "clinical_review",
    "pharmacy_benefits",
}


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Healthcare text to analyze")
    context: str = Field(default="general", max_length=100, description="Processing context")
    user_id: str = Field(..., min_length=1, max_length=100, description="Requesting user identifier")

    @field_validator("user_id")
    @classmethod
    def user_id_alphanumeric(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("user_id must contain only alphanumeric characters, underscores, or hyphens")
        return v

    @field_validator("context")
    @classmethod
    def context_allowlist(cls, v: str) -> str:
        if v not in ALLOWED_CONTEXTS:
            raise ValueError(f"context must be one of: {', '.join(sorted(ALLOWED_CONTEXTS))}")
        return v


class AnalyzeResponse(BaseModel):
    masked_text: str
    pii_detected: List[str]
    ai_response: str
    hallucination_score: float
    hallucination_risk: HallucinationRisk
    toxicity_score: float
    audit_id: str
    processing_ms: int
    warning: Optional[str] = None


class AuditLogEntry(BaseModel):
    id: str
    created_at: str
    user_id: str
    context: str
    input_hash: str
    output_hash: str
    pii_detected: List[str]
    hallucination_score: float
    hallucination_risk: str
    toxicity_score: float
    model_used: str
    processing_ms: int
    masked_text: str
    ai_response: str


class BiasMetricResult(BaseModel):
    demographic_group: str
    metric_name: str
    metric_value: float
    flagged: bool


class BiasReportResponse(BaseModel):
    report_period: str
    total_predictions: int
    demographic_parity_difference: float
    disparate_impact_ratio: float
    flagged_groups: List[str]
    metrics: List[BiasMetricResult]
    compliant: bool


class HealthResponse(BaseModel):
    status: str
    db: str
    model: str
    environment: str

"""
FastAPI Application — Responsible AI Healthcare Framework

Full 7-step pipeline per request:
  [1] Input validation (Pydantic + size limits + prompt injection check)
  [2] PII masking (Presidio + healthcare regex)
  [3] LLM call (Groq / Llama 3 — receives ONLY masked text)
  [4] Toxicity filter (on LLM output)
  [5] Hallucination guard (self-consistency scoring, N=3 samples)
  [6] Risk-based response (HIGH risk → safe fallback)
  [7] Audit log (append-only → Supabase, SHA-256 hashing)

Security: CORS restricted, request size limited, no stack traces exposed.
"""
import time
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    BiasReportResponse,
    BiasMetricResult,
    HealthResponse,
    HallucinationRisk,
)
from app.pii_masker import PIIMasker
from app.guardrails import HallucinationGuard
from app.audit_logger import AuditLogger
from app.bias_metrics import BiasMetrics
from app.toxicity_filter import ToxicityFilter
from app.config import get_settings

# ---------------------------------------------------------------------------
# Logging setup — structured JSON-style
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App startup — initialize all components once
# ---------------------------------------------------------------------------
settings = get_settings()

# Lazy-initialized components
_groq_client = None
_pii_masker: Optional[PIIMasker] = None
_hallucination_guard: Optional[HallucinationGuard] = None
_audit_logger: Optional[AuditLogger] = None
_toxicity_filter: Optional[ToxicityFilter] = None
_bias_metrics: Optional[BiasMetrics] = None


def _init_components():
    global _groq_client, _pii_masker, _hallucination_guard
    global _audit_logger, _toxicity_filter, _bias_metrics

    # PII Masker — always initialized
    _pii_masker = PIIMasker()

    # Toxicity Filter — always initialized
    _toxicity_filter = ToxicityFilter()

    # Bias Metrics — always initialized
    _bias_metrics = BiasMetrics()

    # Groq client — only if key is configured
    if settings.groq_api_key and not settings.groq_api_key.startswith("gsk_your"):
        try:
            from groq import Groq
            _groq_client = Groq(api_key=settings.groq_api_key)
            _hallucination_guard = HallucinationGuard(
                _groq_client,
                settings.groq_model,
                n_samples=settings.hallucination_samples,
            )
            logger.info(f"Groq client initialized. Model: {settings.groq_model}")
        except Exception as e:
            logger.warning(f"Groq initialization failed: {e}. Demo mode active.")
    else:
        logger.info("No Groq API key configured. Running in demo mode.")

    # Audit Logger — with Supabase if configured
    _audit_logger = AuditLogger(settings.supabase_url, settings.supabase_service_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Responsible AI Healthcare API...")
    _init_components()
    logger.info("All components initialized.")
    yield
    logger.info("Shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Responsible AI Healthcare API",
    description=(
        "A production-grade framework for safe, auditable, HIPAA-aligned AI "
        "in healthcare. Provides PII masking, hallucination detection, bias metrics, "
        "toxicity filtering, and immutable audit logging."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — only allow configured origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
    allow_credentials=False,
)

# ---------------------------------------------------------------------------
# System prompt — tuned for healthcare PBM context
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a responsible AI assistant for healthcare claims and pharmacy benefit management (PBM).

Rules you must follow:
1. Only answer based on established clinical guidelines, formulary rules, or CMS requirements.
2. If you are uncertain about any aspect of your answer, say so explicitly — do NOT guess.
3. Never speculate about individual patient outcomes or make clinical recommendations.
4. Cite the type of guideline you are drawing from (e.g., CMS Part D, formulary tier rules, prior auth criteria).
5. Keep responses concise, factual, and professional.
6. If a question is outside your knowledge or requires real-time formulary data, say so clearly.
7. Never provide dosing advice — direct such questions to a licensed pharmacist or physician."""


# ---------------------------------------------------------------------------
# Global exception handler — no internal details exposed to client
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Contact support with your audit_id if available."},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Health check endpoint. Verifies DB connectivity and model status."""
    db_status = "ok"
    if _audit_logger and _audit_logger._client:
        try:
            _audit_logger._client.table("audit_logs").select("id").limit(1).execute()
        except Exception:
            db_status = "error"
    elif not _audit_logger or not _audit_logger._client:
        db_status = "memory_only"

    return HealthResponse(
        status="ok" if db_status in ("ok", "memory_only") else "degraded",
        db=db_status,
        model=settings.groq_model,
        environment=settings.app_env,
    )


@app.post("/api/v1/analyze", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze(request: AnalyzeRequest):
    """
    Run healthcare text through the full 7-step responsible AI pipeline.

    Steps:
    1. Validate input + check prompt injection
    2. Mask PII/PHI before any LLM call
    3. Call Groq LLM (only receives masked text)
    4. Run toxicity filter on output
    5. Score hallucination risk via self-consistency
    6. Apply risk-based response (HIGH → safe fallback)
    7. Write immutable audit log
    """
    start = time.time()

    # --- Step 1: Prompt injection check ---
    if _pii_masker and _pii_masker.check_prompt_injection(request.text):
        raise HTTPException(
            status_code=400,
            detail="Request contains patterns that may indicate a prompt injection attempt.",
        )

    # --- Step 2: PII masking ---
    masked_text, pii_detected = _pii_masker.mask(request.text)
    logger.info(f"PII detected: {pii_detected} | User: {request.user_id}")

    # --- Step 3: LLM call (masked text only) ---
    warning = None
    if _groq_client:
        prompt = f"Context: {request.context}\n\nQuery: {masked_text}"
        try:
            completion = _groq_client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=600,
            )
            ai_response = completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            raise HTTPException(status_code=503, detail="LLM service temporarily unavailable.")
    else:
        # Demo mode — return a realistic simulated response
        ai_response = _demo_response(request.context, masked_text)
        warning = "Demo mode: Groq API key not configured. Response is simulated."
        prompt = f"Context: {request.context}\n\nQuery: {masked_text}"

    # --- Step 4: Toxicity filter ---
    toxicity_score = _toxicity_filter.score(ai_response)
    if toxicity_score >= 0.8:
        logger.warning(f"Response blocked by toxicity filter. Score: {toxicity_score}")
        raise HTTPException(
            status_code=422,
            detail="Response was flagged by the safety filter and has been blocked.",
        )

    # --- Step 5 & 6: Hallucination guard ---
    if _hallucination_guard:
        h_score, h_risk, ai_response = _hallucination_guard.evaluate(prompt, ai_response)
    else:
        # Demo mode — simulate low hallucination risk
        h_score = 0.12
        h_risk = HallucinationRisk.LOW

    # --- Step 7: Audit log ---
    processing_ms = int((time.time() - start) * 1000)
    audit_id = _audit_logger.log(
        user_id=request.user_id,
        context=request.context,
        original_text=request.text,
        masked_text=masked_text,
        ai_response=ai_response,
        pii_detected=pii_detected,
        hallucination_score=h_score,
        hallucination_risk=h_risk,
        toxicity_score=toxicity_score,
        model_used=settings.groq_model if _groq_client else "demo_mode",
        processing_ms=processing_ms,
    )

    logger.info(
        f"Analysis complete | audit_id={audit_id} | "
        f"risk={h_risk.value} | pii={len(pii_detected)} types | {processing_ms}ms"
    )

    return AnalyzeResponse(
        masked_text=masked_text,
        pii_detected=pii_detected,
        ai_response=ai_response,
        hallucination_score=h_score,
        hallucination_risk=h_risk,
        toxicity_score=toxicity_score,
        audit_id=audit_id,
        processing_ms=processing_ms,
        warning=warning,
    )


@app.get("/api/v1/audit/{audit_id}", tags=["Audit"])
async def get_audit(audit_id: str):
    """Retrieve a specific audit log entry by ID."""
    record = _audit_logger.get(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Audit record '{audit_id}' not found.")
    return record


@app.get("/api/v1/audit", tags=["Audit"])
async def list_audit(limit: int = 20):
    """List the most recent audit log entries."""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")
    records = _audit_logger.get_recent(limit=limit)
    return {"count": len(records), "records": records}


@app.get("/api/v1/bias-report", tags=["Bias"])
async def bias_report():
    """
    Return AI fairness metrics from simulated claims data.
    In production this would use actual audit log demographic data.
    """
    # Simulated dataset — realistic claims adjudication scenario
    import random
    random.seed(42)

    groups = ["GroupA", "GroupB", "GroupC", "GroupD"]
    # Simulate realistic approval rate disparities
    approval_rates = {"GroupA": 0.82, "GroupB": 0.78, "GroupC": 0.71, "GroupD": 0.68}

    predictions, group_labels = [], []
    for grp, rate in approval_rates.items():
        n = random.randint(80, 120)
        for _ in range(n):
            predictions.append(1 if random.random() < rate else 0)
            group_labels.append(grp)

    report = _bias_metrics.compute(predictions, group_labels)

    return BiasReportResponse(
        report_period="last_30_days",
        total_predictions=report.total_predictions,
        demographic_parity_difference=report.demographic_parity_difference,
        disparate_impact_ratio=report.disparate_impact_ratio,
        flagged_groups=report.flagged_groups,
        metrics=[
            BiasMetricResult(
                demographic_group=gm.group,
                metric_name="approval_rate",
                metric_value=gm.approval_rate,
                flagged=gm.group in report.flagged_groups,
            )
            for gm in report.group_metrics
        ],
        compliant=report.compliant,
    )


# ---------------------------------------------------------------------------
# Demo mode helper
# ---------------------------------------------------------------------------
DEMO_RESPONSES = {
    "claims_adjudication": (
        "Based on standard formulary adjudication rules, denials for this medication class "
        "typically occur due to: (1) Formulary tier placement requiring step therapy, "
        "(2) Missing prior authorization for brand-name drugs when generics are available, "
        "or (3) Quantity limit restrictions per the plan's clinical criteria. "
        "Per CMS Part D guidelines, the member has the right to request a coverage determination "
        "or exception through their plan's grievance process."
    ),
    "prior_authorization": (
        "Prior authorization requirements for this drug class are typically based on: "
        "(1) Step therapy — failure or contraindication to first-line agents must be documented, "
        "(2) Diagnosis criteria — ICD-10 codes must align with FDA-approved indications, "
        "(3) Prescriber specialty requirements for certain biologics. "
        "Documentation needed: clinical notes, lab values, and prior treatment history."
    ),
    "formulary": (
        "Formulary placement is determined by the plan's Pharmacy and Therapeutics (P&T) "
        "committee based on clinical efficacy, safety profile, and cost-effectiveness. "
        "Tier placement affects member cost-sharing. Formulary exceptions may be requested "
        "if the formulary alternative is clinically contraindicated for the member."
    ),
    "general": (
        "Based on standard healthcare coverage guidelines, this query relates to pharmacy "
        "benefit management protocols. Coverage decisions follow the plan's Evidence of Coverage "
        "(EOC) document and applicable CMS regulations. For specific coverage determinations, "
        "please consult the plan's member services or submit a formal coverage inquiry."
    ),
}


def _demo_response(context: str, masked_text: str) -> str:
    return DEMO_RESPONSES.get(context, DEMO_RESPONSES["general"])

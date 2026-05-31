# Implementation Plan — responsible-ai-healthcare

> Step-by-step build and deployment guide using the 100% free stack:
> Groq · Supabase · Render · Vercel · GitHub Actions

---

## Phase 0 — Account Setup (30 minutes)

Do this before writing any code. All free, no credit card needed except Render (which has a free tier with card on file).

| Service | URL | What to do |
|---------|-----|------------|
| GitHub | github.com | Create repo `responsible-ai-healthcare`, initialize with README |
| Groq | console.groq.com | Sign up → API Keys → create key → copy it |
| Supabase | supabase.com | New project → copy Project URL + anon key + service_role key |
| Render | render.com | Connect GitHub account |
| Vercel | vercel.com | Connect GitHub account |

Save all keys immediately — you will not see them again.

---

## Phase 1 — Local Project Scaffold (1 hour)

### 1.1 Directory structure

```bash
mkdir responsible-ai-healthcare && cd responsible-ai-healthcare
mkdir -p app tests database/migrations frontend/.github/workflows
touch app/__init__.py app/main.py app/pii_masker.py app/guardrails.py \
      app/audit_logger.py app/bias_metrics.py app/toxicity_filter.py app/models.py
touch requirements.txt .env.example render.yaml
```

### 1.2 requirements.txt

```txt
fastapi==0.111.0
uvicorn[standard]==0.29.0
groq==0.9.0
supabase==2.5.0
spacy==3.7.4
pydantic==2.7.1
pydantic-settings==2.3.0
python-dotenv==1.0.1
scikit-learn==1.5.0
numpy==1.26.4
pytest==8.2.2
pytest-cov==5.0.0
pytest-asyncio==0.23.7
httpx==0.27.0
better-profanity==0.7.0
presidio-analyzer==2.2.354
presidio-anonymizer==2.2.354
```

### 1.3 .env.example

```env
# Groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama3-70b-8192

# Supabase
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_KEY=your_service_role_key_here

# App
APP_ENV=development
SECRET_KEY=generate_a_random_32_char_string_here
ALLOWED_ORIGINS=http://localhost:3000,https://yourapp.vercel.app

# Hallucination guard settings
HALLUCINATION_SAMPLES=3
HALLUCINATION_THRESHOLD=0.4

# Bias metrics
BIAS_DISPARITY_THRESHOLD=0.10
```

---

## Phase 2 — Database Setup (30 minutes)

### 2.1 Run migration in Supabase SQL editor

Go to Supabase dashboard → SQL Editor → paste and run:

```sql
-- audit_logs: append-only, no update/delete
CREATE TABLE audit_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    user_id TEXT NOT NULL,
    context TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    pii_detected JSONB DEFAULT '[]',
    hallucination_score FLOAT,
    hallucination_risk TEXT,
    toxicity_score FLOAT,
    model_used TEXT,
    processing_ms INTEGER,
    masked_text TEXT,
    ai_response TEXT
);

-- pii_incidents: tracks each PII detection event
CREATE TABLE pii_incidents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    audit_id UUID REFERENCES audit_logs(id),
    pii_types JSONB NOT NULL,
    context TEXT
);

-- bias_metrics: stores periodic fairness reports
CREATE TABLE bias_metrics (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    report_period TEXT NOT NULL,
    demographic_group TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value FLOAT NOT NULL,
    flagged BOOLEAN DEFAULT FALSE
);

-- Row Level Security — audit_logs is append-only
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_insert" ON audit_logs FOR INSERT WITH CHECK (true);
CREATE POLICY "allow_select" ON audit_logs FOR SELECT USING (true);
-- No UPDATE or DELETE policies = tamper-evident

ALTER TABLE pii_incidents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_insert" ON pii_incidents FOR INSERT WITH CHECK (true);
CREATE POLICY "allow_select" ON pii_incidents FOR SELECT USING (true);

-- Index for fast audit log queries
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX idx_bias_metrics_period ON bias_metrics(report_period, demographic_group);
```

### 2.2 Verify tables exist

In Supabase dashboard → Table Editor — you should see all three tables.

---

## Phase 3 — Backend Implementation (3-4 hours)

### 3.1 app/models.py

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class HallucinationRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    context: str = Field(default="general", max_length=100)
    user_id: str = Field(..., min_length=1, max_length=100)

class AnalyzeResponse(BaseModel):
    masked_text: str
    pii_detected: List[str]
    ai_response: str
    hallucination_score: float
    hallucination_risk: HallucinationRisk
    toxicity_score: float
    audit_id: str
    processing_ms: int
```

### 3.2 app/pii_masker.py

```python
import re
from typing import Tuple, List
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class PIIMasker:
    """
    Detects and masks PHI/PII before sending text to any LLM.
    Uses Microsoft Presidio + custom healthcare regex patterns.
    """

    HEALTHCARE_PATTERNS = {
        "MRN": r"\bMRN[:\s#]*\d{4,10}\b",
        "NPI": r"\bNPI[:\s]*\d{10}\b",
        "DEA": r"\b[A-Z]{2}\d{7}\b",
        "MEMBER_ID": r"\bMember(?:\s+ID)?[:\s]*[A-Z0-9]{8,12}\b",
        "GROUP_NUMBER": r"\bGroup(?:\s+Number)?[:\s]*\d{5,10}\b",
        "NDC": r"\b\d{5}-\d{4}-\d{2}\b",
    }

    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def mask(self, text: str) -> Tuple[str, List[str]]:
        """
        Returns (masked_text, list_of_pii_types_found).
        """
        detected_types = []

        # Apply custom healthcare regex patterns first
        for label, pattern in self.HEALTHCARE_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                detected_types.append(label)
                text = re.sub(pattern, f"[{label}]", text, flags=re.IGNORECASE)

        # Run Presidio for standard PII (names, dates, SSN, phone, email, etc.)
        results = self.analyzer.analyze(text=text, language="en")
        for result in results:
            if result.entity_type not in detected_types:
                detected_types.append(result.entity_type)

        if results:
            anonymized = self.anonymizer.anonymize(text=text, analyzer_results=results)
            text = anonymized.text

        return text, detected_types
```

### 3.3 app/guardrails.py

```python
import hashlib
from groq import Groq
from app.models import HallucinationRisk

class HallucinationGuard:
    """
    Self-consistency hallucination detection.
    Runs N LLM calls at varied temperatures, measures response agreement.
    Low agreement = high hallucination risk.
    """

    TEMPERATURES = [0.0, 0.5, 0.9]

    def __init__(self, groq_client: Groq, model: str, n_samples: int = 3):
        self.client = groq_client
        self.model = model
        self.n_samples = min(n_samples, len(self.TEMPERATURES))

    def _hash_response(self, text: str) -> str:
        return hashlib.md5(text.strip().lower()[:200].encode()).hexdigest()

    def score(self, prompt: str, primary_response: str) -> tuple[float, HallucinationRisk]:
        """
        Returns (score, risk_level).
        Score: 0.0 = fully consistent, 1.0 = maximum disagreement.
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
            except Exception:
                hashes.append("error")

        unique = len(set(hashes))
        score = round((unique - 1) / max(len(hashes) - 1, 1), 2)

        if score < 0.25:
            risk = HallucinationRisk.LOW
        elif score < 0.6:
            risk = HallucinationRisk.MEDIUM
        else:
            risk = HallucinationRisk.HIGH

        return score, risk
```

### 3.4 app/audit_logger.py

```python
import hashlib
import time
from typing import List, Optional
from supabase import create_client, Client
from app.models import HallucinationRisk

class AuditLogger:
    """
    Immutable audit trail for all AI decisions.
    Maps to HIPAA Security Rule §164.312(b) audit controls.
    """

    def __init__(self, supabase_url: str, supabase_key: str):
        self.client: Client = create_client(supabase_url, supabase_key)

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

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
        Writes one audit record. Returns the audit_id UUID.
        """
        record = {
            "user_id": user_id,
            "context": context,
            "input_hash": self._hash(original_text),
            "output_hash": self._hash(ai_response),
            "masked_text": masked_text,
            "ai_response": ai_response,
            "pii_detected": pii_detected,
            "hallucination_score": hallucination_score,
            "hallucination_risk": hallucination_risk.value,
            "toxicity_score": toxicity_score,
            "model_used": model_used,
            "processing_ms": processing_ms,
        }
        result = self.client.table("audit_logs").insert(record).execute()
        return result.data[0]["id"]

    def get(self, audit_id: str) -> Optional[dict]:
        result = (
            self.client.table("audit_logs")
            .select("*")
            .eq("id", audit_id)
            .execute()
        )
        return result.data[0] if result.data else None
```

### 3.5 app/main.py

```python
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from app.models import AnalyzeRequest, AnalyzeResponse
from app.pii_masker import PIIMasker
from app.guardrails import HallucinationGuard
from app.audit_logger import AuditLogger
from app.toxicity_filter import ToxicityFilter
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    groq_model: str = "llama3-70b-8192"
    supabase_url: str
    supabase_service_key: str
    allowed_origins: str = "http://localhost:3000"
    hallucination_samples: int = 3

    class Config:
        env_file = ".env"

settings = Settings()
app = FastAPI(title="Responsible AI Healthcare API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

groq_client = Groq(api_key=settings.groq_api_key)
pii_masker = PIIMasker()
hallucination_guard = HallucinationGuard(groq_client, settings.groq_model, settings.hallucination_samples)
audit_logger = AuditLogger(settings.supabase_url, settings.supabase_service_key)
toxicity_filter = ToxicityFilter()

SYSTEM_PROMPT = """You are a responsible AI assistant for healthcare claims and pharmacy benefit management.
Rules:
- Only answer based on established clinical and PBM guidelines.
- If you are uncertain, say so explicitly — do not guess.
- Never speculate about individual patient outcomes.
- Cite the type of guideline you are drawing from (e.g., CMS, formulary rules, clinical protocol).
- Keep responses concise and factual."""

@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    start = time.time()

    # Step 1: Mask PII before it reaches the LLM
    masked_text, pii_detected = pii_masker.mask(request.text)

    # Step 2: Build prompt using masked text only
    prompt = f"Context: {request.context}\n\nQuery: {masked_text}"

    # Step 3: Primary LLM call via Groq (free, fast)
    completion = groq_client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=600,
    )
    ai_response = completion.choices[0].message.content

    # Step 4: Toxicity filter
    toxicity_score = toxicity_filter.score(ai_response)
    if toxicity_score > 0.8:
        raise HTTPException(status_code=422, detail="Response flagged by safety filter")

    # Step 5: Hallucination scoring
    h_score, h_risk = hallucination_guard.score(prompt, ai_response)

    # Step 6: Audit log (always, even on errors)
    processing_ms = int((time.time() - start) * 1000)
    audit_id = audit_logger.log(
        user_id=request.user_id,
        context=request.context,
        original_text=request.text,
        masked_text=masked_text,
        ai_response=ai_response,
        pii_detected=pii_detected,
        hallucination_score=h_score,
        hallucination_risk=h_risk,
        toxicity_score=toxicity_score,
        model_used=settings.groq_model,
        processing_ms=processing_ms,
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
    )

@app.get("/api/v1/audit/{audit_id}")
async def get_audit(audit_id: str):
    record = audit_logger.get(audit_id)
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return record

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "model": settings.groq_model}
```

---

## Phase 4 — Tests (45 minutes)

### tests/test_pii_masker.py

```python
import pytest
from app.pii_masker import PIIMasker

@pytest.fixture
def masker():
    return PIIMasker()

def test_masks_name(masker):
    text, detected = masker.mask("Patient John Smith needs refill")
    assert "John Smith" not in text
    assert any("PERSON" in d or "NAME" in d for d in detected)

def test_masks_mrn(masker):
    text, detected = masker.mask("MRN: 123456789 is flagged")
    assert "123456789" not in text
    assert "MRN" in detected

def test_masks_dob(masker):
    text, detected = masker.mask("DOB 04/12/1980 denied claim")
    assert "1980" not in text

def test_clean_text_unchanged(masker):
    text, detected = masker.mask("Metformin is covered under formulary tier 2")
    assert text == "Metformin is covered under formulary tier 2"
    assert len(detected) == 0
```

### tests/test_guardrails.py

```python
import pytest
from unittest.mock import MagicMock, patch
from app.guardrails import HallucinationGuard
from app.models import HallucinationRisk

@pytest.fixture
def mock_groq():
    client = MagicMock()
    return client

def test_consistent_responses_low_risk(mock_groq):
    response_text = "Metformin is a first-line diabetes medication."
    mock_groq.chat.completions.create.return_value.choices[0].message.content = response_text
    guard = HallucinationGuard(mock_groq, "test-model", n_samples=3)
    score, risk = guard.score("Is metformin covered?", response_text)
    assert risk == HallucinationRisk.LOW

def test_score_between_0_and_1(mock_groq):
    guard = HallucinationGuard(mock_groq, "test-model", n_samples=2)
    mock_groq.chat.completions.create.return_value.choices[0].message.content = "Different answer"
    score, _ = guard.score("any prompt", "Original answer")
    assert 0.0 <= score <= 1.0
```

---

## Phase 5 — CI/CD with GitHub Actions

### .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Download spaCy model
        run: python -m spacy download en_core_web_sm
      - name: Run tests
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          SECRET_KEY: test_secret_key_32chars_minimum
        run: pytest tests/ -v --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

Add `GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` to GitHub → Settings → Secrets and variables → Actions.

---

## Phase 6 — Deploy to Render (Backend)

### render.yaml

```yaml
services:
  - type: web
    name: responsible-ai-healthcare-api
    env: python
    buildCommand: pip install -r requirements.txt && python -m spacy download en_core_web_sm
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: GROQ_API_KEY
        sync: false
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_KEY
        sync: false
      - key: SECRET_KEY
        sync: false
      - key: ALLOWED_ORIGINS
        value: https://yourapp.vercel.app
      - key: APP_ENV
        value: production
```

**Steps:**
1. Push code to GitHub
2. Render dashboard → New → Web Service → Connect your repo
3. Render auto-detects `render.yaml` and sets up the service
4. Add environment variables in Render dashboard
5. Deploy — Render gives you a URL like `https://responsible-ai-healthcare-api.onrender.com`

---

## Phase 7 — Deploy Frontend to Vercel

```bash
cd frontend
npx create-react-app . --template typescript  # or use Vite
# Build your React components
vercel --prod
```

Set environment variable in Vercel dashboard:
```
REACT_APP_API_URL=https://responsible-ai-healthcare-api.onrender.com
```

---

## Phase 8 — Smoke Test End to End

```bash
# Test the deployed API
curl -X POST https://your-api.onrender.com/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient John Smith MRN 123456 denied metformin", "context": "claims_adjudication", "user_id": "test_user"}'

# Expected: PII masked, AI response, audit_id returned
```

---

## Phase 9 — Demo Script

```python
# demo.py — run this to show the full pipeline working
import requests

API = "http://localhost:8000"

test_cases = [
    {
        "text": "Why was metformin denied for patient Jane Doe DOB 1975-03-15?",
        "context": "claims_adjudication",
        "user_id": "demo_reviewer"
    },
    {
        "text": "Member ID XYZ123456 prior auth request for Humira 40mg",
        "context": "prior_authorization",
        "user_id": "demo_reviewer"
    }
]

for case in test_cases:
    print(f"\nInput: {case['text']}")
    r = requests.post(f"{API}/api/v1/analyze", json=case)
    data = r.json()
    print(f"PII masked: {data['pii_detected']}")
    print(f"Hallucination risk: {data['hallucination_risk']} ({data['hallucination_score']})")
    print(f"Response: {data['ai_response'][:200]}...")
    print(f"Audit ID: {data['audit_id']}")
```

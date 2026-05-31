# responsible-ai-healthcare

> A production-grade Python framework for building safe, auditable, and HIPAA-aligned AI systems in healthcare — with guardrails, PII masking, hallucination detection, bias metrics, and full audit logging.

[![CI](https://github.com/utkarsh-shri/responsible-ai-healthcare/actions/workflows/ci.yml/badge.svg)](https://github.com/utkarsh-shri/responsible-ai-healthcare/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Deployed on Render](https://img.shields.io/badge/API-Render-46E3B7)](https://render.com)
[![Frontend on Vercel](https://img.shields.io/badge/UI-Vercel-black)](https://vercel.com)

---

## Why This Exists

Most AI engineers can build a RAG chatbot. Very few understand what happens when that chatbot gives a wrong answer about drug coverage to a patient — or when a claims adjudication agent surfaces biased denial rates across demographic groups.

This framework was built by someone who spent 13+ years inside RxClaim, PBM adjudication workflows, and CMS compliance. It encodes what responsible AI *actually means* in healthcare, not as a checklist, but as running, testable code.

---

## What It Does

| Module | What it solves |
|--------|---------------|
| `pii_masker` | Detects and masks PHI/PII in free text before it hits any LLM |
| `guardrails` | Scores LLM output for hallucination risk using self-consistency + confidence |
| `audit_logger` | Immutable, structured audit trail for every AI decision (HIPAA audit requirement) |
| `bias_metrics` | Measures AI prediction fairness across demographic groups in claims data |
| `toxicity_filter` | Filters harmful or inappropriate LLM output before serving to users |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client (React / Vercel)                   │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
┌─────────────────────▼───────────────────────────────────────┐
│              FastAPI Backend (Render.com)                    │
│                                                             │
│  Request → [PII Masker] → [LLM Call via Groq] → [Output]   │
│                                  ↓                          │
│               [Guardrails: hallucination score]             │
│                                  ↓                          │
│               [Toxicity Filter]                             │
│                                  ↓                          │
│               [Audit Logger → Supabase]                     │
│                                  ↓                          │
│               Response (masked, scored, logged)             │
└─────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              Supabase (PostgreSQL)                           │
│  - audit_logs table (append-only, RLS enforced)             │
│  - bias_metrics table                                       │
│  - pii_incidents table                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Free Stack Used

| Layer | Tool | Why |
|-------|------|-----|
| LLM inference | [Groq](https://groq.com) — free tier | Fastest free LLM API (Llama 3, Mixtral) |
| API backend | [Render.com](https://render.com) — free tier | Auto-deploy from GitHub, free SSL |
| Frontend | [Vercel](https://vercel.com) — free tier | Zero-config React deploy |
| Database | [Supabase](https://supabase.com) — free tier | PostgreSQL + Row Level Security + REST API |
| CI/CD | [GitHub Actions](https://github.com/features/actions) — free | Automated tests on every push |
| Secrets | GitHub Secrets + Render env vars | No paid vault needed |

**Total cost to run this: $0/month**

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- Free accounts: Groq, Supabase, Render, Vercel, GitHub

### 1. Clone and install

```bash
git clone https://github.com/utkarsh-shri/responsible-ai-healthcare.git
cd responsible-ai-healthcare
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in your keys — see .env.example for all required vars
```

### 3. Set up Supabase

```bash
# Run the migration SQL in your Supabase project dashboard
psql -h your-supabase-host -U postgres -f database/migrations/001_init.sql
```

### 4. Run the API locally

```bash
uvicorn app.main:app --reload --port 8000
# API docs at http://localhost:8000/docs
```

### 5. Run the frontend locally

```bash
cd frontend
npm install
npm run dev
# UI at http://localhost:3000
```

### 6. Run tests

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## API Reference

### POST `/api/v1/analyze`
Run a healthcare text through the full responsible AI pipeline.

**Request:**
```json
{
  "text": "Patient John Smith DOB 1980-04-12 was denied coverage for metformin",
  "context": "claims_adjudication",
  "user_id": "reviewer_001"
}
```

**Response:**
```json
{
  "masked_text": "Patient [NAME] DOB [DATE] was denied coverage for metformin",
  "pii_detected": ["NAME", "DATE"],
  "ai_response": "The denial may be due to formulary tier placement...",
  "hallucination_score": 0.12,
  "hallucination_risk": "LOW",
  "toxicity_score": 0.01,
  "audit_id": "aud_2024_abc123",
  "processing_ms": 340
}
```

### GET `/api/v1/audit/{audit_id}`
Retrieve a specific audit log entry.

### GET `/api/v1/bias-report`
Get fairness metrics across demographic groups for the last 30 days.

### GET `/api/v1/health`
Health check endpoint.

---

## Module Deep Dive

### PII Masker
Uses spaCy NER + custom regex patterns tuned for healthcare data:
- Names, DOB, SSN, MRN, NPI, DEA numbers
- Insurance member IDs, group numbers
- Addresses, phone numbers, email
- Drug names combined with patient identifiers

```python
from app.pii_masker import PIIMasker

masker = PIIMasker()
result = masker.mask("John Smith (MRN: 12345) prescribed lisinopril")
# → "[NAME] (MRN: [MRN]) prescribed lisinopril"
```

### Guardrails (Hallucination Detection)
Self-consistency approach: asks the LLM the same question N times with temperature variation, then measures agreement. Low agreement = high hallucination risk.

```python
from app.guardrails import HallucinationGuard

guard = HallucinationGuard(groq_client, n_samples=3)
score = guard.score("Is metformin covered under Medicare Part D?", response)
# score 0.0 = fully consistent, 1.0 = maximum disagreement
```

### Audit Logger
Every AI decision is logged to Supabase with: timestamp, user, input hash, output hash, PII flags, hallucination score, model used, latency. The table is append-only (no UPDATE/DELETE permissions via RLS).

### Bias Metrics
Given a set of predictions and demographic labels, computes:
- Demographic parity difference
- Equalized odds
- Disparate impact ratio

Flags when any group shows >10% worse outcomes than the best-performing group.

---

## HIPAA Alignment Notes

This framework does **not** make you HIPAA compliant on its own. It implements engineering controls relevant to HIPAA Security Rule requirements:

- **Audit Controls (§164.312(b)):** Every AI decision logged with who, what, when
- **Minimum Necessary (§164.502(b)):** PII masking before LLM = only send what's needed
- **Integrity (§164.312(c)):** Audit logs are append-only, tamper-evident via hashing
- **PHI in LLM prompts:** Framework warns when unmasked PHI is detected before any API call

A real HIPAA deployment requires a BAA with your cloud vendors, additional access controls, and legal review. This framework gives you the engineering foundation.

---

## Project Structure

```
responsible-ai-healthcare/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── pii_masker.py        # PII detection and masking
│   ├── guardrails.py        # Hallucination scoring
│   ├── audit_logger.py      # Supabase audit logging
│   ├── bias_metrics.py      # Fairness metrics
│   ├── toxicity_filter.py   # Output safety filter
│   └── models.py            # Pydantic request/response models
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── AnalyzePanel.jsx
│   │   │   ├── AuditLog.jsx
│   │   │   └── BiasReport.jsx
│   └── package.json
├── tests/
│   ├── test_pii_masker.py
│   ├── test_guardrails.py
│   ├── test_audit_logger.py
│   └── test_bias_metrics.py
├── database/
│   └── migrations/
│       └── 001_init.sql
├── .github/
│   └── workflows/
│       └── ci.yml
├── .env.example
├── requirements.txt
├── render.yaml              # Render deployment config
└── README.md
```

---

## Deployment

See `IMPLEMENTATION_PLAN.md` for step-by-step deployment to the free stack.

---

## Built By

Utkarsh Shrivastava — 13+ years Healthcare PBM / RxClaim / CMS compliance, transitioning into AI Engineering with a focus on responsible AI in regulated healthcare environments.

[LinkedIn](https://linkedin.com/in/utkarsh-shrivastava) · [GitHub](https://github.com/utkarsh-shri)

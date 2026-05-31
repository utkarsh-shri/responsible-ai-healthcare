# Project Brief — responsible-ai-healthcare

**Version:** 1.0  
**Author:** Utkarsh Shrivastava  
**Status:** Portfolio project — actively under development  
**Repo:** github.com/yourusername/responsible-ai-healthcare

---

## One-Line Description

A reusable Python framework that adds PII masking, hallucination detection, bias metrics, and immutable audit logging to any healthcare AI system — built by someone who spent 13 years understanding why those guardrails matter.

---

## Problem Statement

Healthcare AI deployments face four compounding risks that general-purpose AI frameworks do not address:

**1. PHI exposure to LLMs**
Every time unmasked patient data reaches an LLM API, it creates HIPAA liability unless covered by a Business Associate Agreement (BAA). Most developer tutorials skip this entirely.

**2. Hallucination in high-stakes decisions**
An LLM that confidently states wrong coverage information can cause a patient to receive the wrong medication, delay care, or incur unexpected costs. Standard chatbot frameworks have no mechanism to flag this.

**3. No audit trail**
HIPAA Security Rule §164.312(b) requires audit controls on systems that access or process protected health information. Most LLM deployments produce zero auditable evidence of what the AI decided and why.

**4. Demographic bias in claims AI**
When AI assists claims adjudication, any bias in training data translates to systematic disparities in denial rates across demographic groups — a regulatory and ethical failure.

This framework provides running, tested code for each of these problems.

---

## Who This Is For

- **Healthcare AI engineers** building LLM-powered applications in PBM, claims, or clinical settings
- **Compliance teams** evaluating AI systems before production deployment
- **AI architects** designing responsible AI patterns for regulated industries
- **Hiring managers at Optum, CVS Health, Humana, BCBS** evaluating candidates who understand both the technology and the regulatory environment

---

## What It Is Not

- A HIPAA compliance solution (legal compliance requires more than engineering controls)
- A replacement for human clinical judgment
- A production-ready product requiring no customization
- A general-purpose AI safety framework (it is specifically tuned for healthcare PBM context)

---

## Domain Expertise Behind the Design

The technical decisions in this framework are informed by direct experience with:

- **RxClaim adjudication engine** — how claims flow through eligibility, formulary, prior auth, and pay/deny decision paths
- **CMS compliance requirements** — what Medicare Part D plans must document for audit
- **PBM workflow edge cases** — DAW codes, step therapy, quantity limits, therapeutic alternatives
- **AS400 / iSeries data architecture** — how legacy healthcare data is structured and where PII lives in unexpected fields

This context shaped decisions like:
- Including NPI and DEA numbers in PII masking (most frameworks don't)
- Designing the audit log schema to match the fields a compliance auditor would ask for
- Tuning the hallucination guard specifically for formulary coverage questions (where factual precision matters more than fluency)
- Including claims-specific contexts in the allowlist (`claims_adjudication`, `prior_authorization`, `formulary`)

---

## Technical Architecture

### Request lifecycle

```
User Input (raw text with potential PHI)
        ↓
[1] Input Validation (Pydantic, size limits, prompt injection check)
        ↓
[2] PII Masker (Presidio + healthcare regex → masked text)
        ↓
[3] LLM Call (Groq / Llama 3 — receives ONLY masked text)
        ↓
[4] Toxicity Filter (profanity + harm detection on output)
        ↓
[5] Hallucination Guard (self-consistency scoring, N=3 samples)
        ↓
[6] Risk-Based Response (HIGH risk → safe fallback message)
        ↓
[7] Audit Logger (append-only → Supabase, SHA-256 hashing)
        ↓
Response to client (masked text, score, risk level, audit_id)
```

### Free infrastructure stack

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Vercel     │    │   Render     │    │  Supabase    │
│  React UI    │───▶│  FastAPI     │───▶│ PostgreSQL   │
│  (free)      │    │  (free)      │    │ audit_logs   │
└──────────────┘    └──────┬───────┘    └──────────────┘
                           │
                    ┌──────▼───────┐
                    │    Groq      │
                    │ Llama 3 70B  │
                    │  (free API)  │
                    └──────────────┘
```

---

## Key Technical Decisions and Rationale

| Decision | Alternative | Why this choice |
|----------|-------------|-----------------|
| Groq for LLM inference | OpenAI GPT-4 | Free tier, fastest inference (~300 tok/s), Llama 3 70B is capable for this domain |
| Presidio for PII detection | Custom regex only | Microsoft Presidio is NLP-based — catches contextual PII that regex misses (e.g., "the patient born in spring of 1980") |
| Supabase for audit logs | SQLite, DynamoDB | PostgreSQL semantics, Row Level Security, REST API, free tier — production-grade without paid infrastructure |
| Self-consistency hallucination scoring | LLM confidence scores | LLM confidence scores are unreliable and self-reported; self-consistency is behaviorally grounded |
| Append-only audit table (RLS, no DELETE) | Standard CRUD table | HIPAA audit integrity — logs must be tamper-evident |
| Render for API hosting | Heroku, Railway | Free tier with persistent service (Heroku removed free tier), simple render.yaml config |

---

## Modules

### `pii_masker`
**What it does:** Runs input text through Microsoft Presidio (NLP-based entity detection) plus custom regex patterns for healthcare-specific identifiers (MRN, NPI, DEA, member ID, group number). Returns masked text and a list of PII types detected.

**Key design choice:** Masking happens before the text ever reaches any LLM call. This is enforced architecturally — the Groq client never receives a function that accepts unmasked text.

### `guardrails`
**What it does:** After the primary LLM response, asks Groq 2 additional times with different temperature settings. Computes agreement across 3 responses. Low agreement → high hallucination risk. Risk levels: LOW / MEDIUM / HIGH.

**Key design choice:** HIGH hallucination risk responses are not returned to the user at all — a safe fallback message is substituted. MEDIUM responses get a warning prepended.

### `audit_logger`
**What it does:** Writes a structured audit record to Supabase for every AI decision. Fields include: user_id, timestamp, input hash (SHA-256), output hash, PII types detected, hallucination score and risk level, toxicity score, model used, latency in ms, masked text, AI response.

**Key design choice:** The Supabase table has Row Level Security configured with INSERT and SELECT policies but no UPDATE or DELETE policies. This makes the log tamper-evident by design.

### `bias_metrics`
**What it does:** Given a dataset of AI predictions and demographic group labels, computes demographic parity difference, equalized odds, and disparate impact ratio. Flags when any group shows >10% worse outcomes than the best-performing group.

**Key design choice:** Threshold of 10% disparity is based on the "4/5ths rule" commonly used in employment discrimination analysis — applied here to claims outcomes.

### `toxicity_filter`
**What it does:** Runs the LLM output through a toxicity classifier before serving it to the user. Uses `better-profanity` for basic filtering plus keyword checks for harmful content categories.

---

## Deliverables

- [ ] Python package (`app/`) with all five modules
- [ ] FastAPI REST API with 4 endpoints
- [ ] React frontend (analyze panel, audit log viewer, bias report)
- [ ] Supabase schema with migrations and RLS policies
- [ ] GitHub Actions CI pipeline (test + lint + security audit)
- [ ] Render deployment config (`render.yaml`)
- [ ] Vercel deployment config (`vercel.json`)
- [ ] Comprehensive test suite (>80% coverage)
- [ ] Demo script showing full pipeline
- [ ] README with ASCII architecture diagram
- [ ] `IMPLEMENTATION_PLAN.md` (step-by-step build guide)
- [ ] `BEST_PRACTICES.md` (security and robustness guide)

---

## Interview Talking Points

Use these when a hiring manager asks "walk me through this project":

**Why did you build this?**
"After 13 years in PBM operations with RxClaim, I saw firsthand what happens when clinical data is handled carelessly in automated systems. When I started building AI projects, I realized most frameworks have no concept of PHI, no audit trail, no way to flag uncertain answers. I built this to demonstrate what responsible AI looks like when you actually understand the healthcare domain."

**What was the hardest technical decision?**
"The hallucination guard design. LLMs don't reliably self-report their own confidence. Self-consistency — running the same prompt multiple times and measuring agreement — is more behaviorally honest. The tradeoff is 3x Groq API calls per request, which is why I use it only after the primary response and why HIGH-risk responses get a safe fallback instead of the AI's answer."

**How does this map to the Optum JD?**
"RAG pipelines and agents are Projects 1 and 2 in my portfolio. This project is the responsible AI layer that would sit above any of those systems. The audit logging maps directly to HIPAA compliance work. The bias metrics map to Optum's equity commitments. The PII masking maps to the data governance concerns any PBM has before touching LLMs."

**What would production version need?**
"A BAA with Groq or a move to Azure OpenAI (which offers BAAs). Fine-tuning or RAG on actual formulary and clinical guideline documents. Role-based access control beyond API key auth. Integration with existing identity providers (Active Directory/Okta). Performance testing under real claims volume. This framework gives you the architecture skeleton — the domain data and enterprise integrations are what makes it production."

---

## Timeline

| Day | Milestone |
|-----|-----------|
| Day 1 AM | Scaffold, Supabase schema, env setup |
| Day 1 PM | PII masker + tests |
| Day 2 AM | Guardrails + audit logger + tests |
| Day 2 PM | FastAPI endpoints + CI pipeline |
| Day 3 AM | React frontend + bias metrics module |
| Day 3 PM | Deploy to Render + Vercel, smoke test, README polish |
| EOD | GitHub pushed, LinkedIn updated, apply |

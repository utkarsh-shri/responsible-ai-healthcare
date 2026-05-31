# Security & Best Practices — responsible-ai-healthcare

> Engineering controls for a secure, robust, production-grade AI system in a regulated healthcare environment. Every item here is implementable on the free stack with zero additional cost.

---

## 1. Secrets Management

### Never hardcode keys. Ever.

```python
# WRONG
groq_client = Groq(api_key="gsk_abc123...")

# RIGHT
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str  # Loaded from env, never from code

    class Config:
        env_file = ".env"
```

### .gitignore — non-negotiable

```gitignore
.env
.env.local
.env.production
*.key
*.pem
__pycache__/
.pytest_cache/
venv/
node_modules/
```

### Secret rotation checklist
- Groq API key: rotate every 90 days, immediately if exposed
- Supabase service key: rotate if any team member leaves
- `SECRET_KEY` (app signing): rotate every 6 months
- Never log secret values — log key *names* only if needed for debugging

---

## 2. Input Validation

### Always validate at the API boundary

```python
from pydantic import BaseModel, Field, validator
import re

class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    context: str = Field(default="general", max_length=100)
    user_id: str = Field(..., min_length=1, max_length=100)

    @validator("user_id")
    def user_id_alphanumeric(cls, v):
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("user_id must be alphanumeric")
        return v

    @validator("context")
    def context_allowlist(cls, v):
        allowed = {"claims_adjudication", "prior_authorization", "formulary", "general"}
        if v not in allowed:
            raise ValueError(f"context must be one of {allowed}")
        return v
```

### Prompt injection defense

```python
PROMPT_INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore all prior",
    r"system prompt",
    r"you are now",
    r"new instructions",
    r"jailbreak",
    r"DAN mode",
]

def check_prompt_injection(text: str) -> bool:
    """Returns True if injection attempt detected."""
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in PROMPT_INJECTION_PATTERNS)
```

### Size limits on all endpoints

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.headers.get("content-length"):
            if int(request.headers["content-length"]) > 50_000:  # 50KB max
                raise HTTPException(status_code=413, detail="Request too large")
        return await call_next(request)
```

---

## 3. Authentication & Authorization

### API key authentication (simple, free, stateless)

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    valid_keys = settings.api_keys.split(",")  # Comma-separated in env
    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
```

Apply to all protected routes:
```python
@app.post("/api/v1/analyze", dependencies=[Depends(verify_api_key)])
async def analyze(request: AnalyzeRequest):
    ...
```

### Supabase Row Level Security — enforce at DB level

```sql
-- Users can only read their own audit logs
CREATE POLICY "users_own_logs" ON audit_logs
    FOR SELECT USING (user_id = current_user);

-- Service role can read all (for admin dashboard)
-- anon role can only insert, never read
```

### Principle of least privilege
- Frontend uses `SUPABASE_ANON_KEY` — read access only, RLS enforced
- Backend uses `SUPABASE_SERVICE_KEY` — full access, never exposed to client
- Groq key — backend only, never in frontend code or browser

---

## 4. PII / PHI Protection

### The PHI-in-LLM problem

Sending unmasked PHI to any LLM (including Groq) creates HIPAA exposure unless you have a BAA. **Always mask before the API call.**

```python
# This order is non-negotiable
masked_text, pii_types = pii_masker.mask(request.text)   # 1. Mask
ai_response = groq_client.chat(prompt=masked_text)         # 2. THEN call LLM
audit_logger.log(masked_text=masked_text, ...)             # 3. Log masked version only
```

### Never log original PHI

```python
# WRONG — logs raw PHI
logger.info(f"Processing request: {request.text}")

# RIGHT — log masked version or hash only
logger.info(f"Processing request hash: {hashlib.sha256(request.text.encode()).hexdigest()[:8]}")
```

### PII masking coverage checklist
- [ ] Full name (first, last, combined)
- [ ] Date of birth
- [ ] Social Security Number
- [ ] Medical Record Number (MRN)
- [ ] National Provider Identifier (NPI)
- [ ] DEA number
- [ ] Member ID / subscriber number
- [ ] Group number
- [ ] Address (street, city, ZIP)
- [ ] Phone number
- [ ] Email address
- [ ] IP address (if logging)

---

## 5. Rate Limiting

### Protect your Groq free tier and prevent abuse

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/v1/analyze")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def analyze(request: Request, body: AnalyzeRequest):
    ...
```

Add `slowapi` to requirements.txt.

### Groq rate limit handling with retry

```python
import time
from groq import RateLimitError

def call_groq_with_retry(client, **kwargs, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

---

## 6. Error Handling

### Never expose internal errors to clients

```python
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log full error internally
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    # Return generic error to client — no stack traces, no internals
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Reference your audit_id if available."}
    )
```

### Structured logging

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        })

# Apply to root logger
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(handlers=[handler], level=logging.INFO)
```

---

## 7. CORS Configuration

### Restrict to known origins only

```python
# WRONG — allows any origin
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# RIGHT — explicit allowlist from environment
origins = settings.allowed_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # e.g. ["https://yourapp.vercel.app"]
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    allow_credentials=False,
)
```

---

## 8. Dependency Security

### Check for vulnerabilities regularly

```bash
# Install safety checker
pip install pip-audit

# Scan your dependencies
pip-audit -r requirements.txt

# Add to CI pipeline
- name: Security audit
  run: pip-audit -r requirements.txt
```

### Pin exact versions in requirements.txt

```txt
# WRONG — unpinned allows breaking changes
fastapi
groq

# RIGHT — exact pins, reproducible builds
fastapi==0.111.0
groq==0.9.0
```

---

## 9. Audit Log Integrity

### Make audit logs tamper-evident

```python
import hashlib

def compute_chain_hash(previous_hash: str, record: dict) -> str:
    """Each audit log entry hashes its own content + previous entry's hash."""
    content = f"{previous_hash}:{record['created_at']}:{record['input_hash']}:{record['output_hash']}"
    return hashlib.sha256(content.encode()).hexdigest()
```

### Supabase backup (free, automated)

In Supabase dashboard → Settings → Database → Enable Point-in-Time Recovery (available on free tier with limitations). For daily backups, set up a GitHub Actions cron job:

```yaml
- name: Backup audit logs
  schedule:
    - cron: "0 2 * * *"  # 2am daily
  run: |
    python scripts/backup_audit_logs.py
```

---

## 10. Hallucination Risk Response Protocol

### Don't just score — act on the score

```python
async def handle_high_risk_response(h_risk, ai_response, context):
    if h_risk == HallucinationRisk.HIGH:
        # Don't return the AI response — return a safe fallback
        return (
            "I am not confident in my answer to this question. "
            "Please consult the official formulary or CMS guidelines directly, "
            "or route this to a human reviewer."
        )
    elif h_risk == HallucinationRisk.MEDIUM:
        # Return response but prepend a warning
        return f"[Note: Confidence in this response is moderate. Verify before acting.]\n\n{ai_response}"
    else:
        return ai_response
```

---

## 11. Frontend Security (React / Vercel)

### Environment variables — never expose secrets to browser

```bash
# Vercel dashboard → Settings → Environment Variables
REACT_APP_API_URL=https://your-api.onrender.com
# Never put GROQ_API_KEY or SUPABASE_SERVICE_KEY here
```

### Content Security Policy headers (add in vercel.json)

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "X-XSS-Protection", "value": "1; mode=block" },
        {
          "key": "Content-Security-Policy",
          "value": "default-src 'self'; connect-src 'self' https://your-api.onrender.com"
        }
      ]
    }
  ]
}
```

---

## 12. Monitoring (Free)

### Health check endpoint — monitored by Render automatically

```python
@app.get("/api/v1/health")
async def health():
    # Check DB connectivity
    try:
        supabase.table("audit_logs").select("id").limit(1).execute()
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "model": settings.groq_model,
    }
```

### UptimeRobot (free) — set up uptime monitoring

1. Go to uptimerobot.com → free account
2. Add monitor → HTTPS → your Render URL + `/api/v1/health`
3. Alert via email when down

---

## Security Checklist Before Going Live

- [ ] `.env` is in `.gitignore` and never committed
- [ ] All secrets in environment variables, not in code
- [ ] Input validation on all endpoints via Pydantic
- [ ] PII masking runs before every LLM call
- [ ] Audit logs are append-only (no UPDATE/DELETE in RLS)
- [ ] CORS restricted to known frontend origin
- [ ] Rate limiting active on all public endpoints
- [ ] Generic error messages to client (no stack traces)
- [ ] `pip-audit` added to CI pipeline
- [ ] All dependency versions pinned
- [ ] Health check endpoint live and monitored
- [ ] HIGH hallucination risk returns safe fallback, not the AI response
- [ ] Frontend has no backend secrets in environment variables
- [ ] CSP headers configured in vercel.json

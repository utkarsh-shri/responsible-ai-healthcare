const STEPS = [
  { id: 1, icon: '🔍', title: 'Input Validation', color: 'var(--color-primary)', desc: 'Pydantic schema validation, size limits (50KB max), and prompt injection detection' },
  { id: 2, icon: '🔒', title: 'PII Masking', color: 'var(--color-warning)', desc: 'Microsoft Presidio NLP + healthcare regex (MRN, NPI, DEA, Member ID). Runs BEFORE any LLM call.' },
  { id: 3, icon: '🤖', title: 'Groq LLM Call', color: 'var(--color-teal)', desc: 'Llama 3 70B via Groq API. Receives only masked text. Temperature 0.1 for factual responses.' },
  { id: 4, icon: '🛡️', title: 'Toxicity Filter', color: 'var(--color-purple)', desc: 'better-profanity + healthcare harm patterns. Score > 0.8 → response blocked entirely.' },
  { id: 5, icon: '🎯', title: 'Hallucination Guard', color: 'var(--color-warning)', desc: 'Self-consistency: 3 LLM calls at varied temperatures. Low agreement = HIGH risk → safe fallback.' },
  { id: 6, icon: '📋', title: 'Audit Logger', color: 'var(--color-success)', desc: 'SHA-256 hashes input + output. Writes to Supabase append-only table (no UPDATE/DELETE via RLS).' },
]

const MODULES = [
  { name: 'pii_masker', badge: 'badge-warning', desc: 'Two-pass: healthcare regex then Presidio NLP. Catches MRN, NPI, DEA, Member ID, and contextual PII.' },
  { name: 'guardrails', badge: 'badge-danger',  desc: 'Self-consistency scoring. N=3 samples at T=[0.0, 0.5, 0.9]. Score = (unique−1)/(N−1).' },
  { name: 'audit_logger', badge: 'badge-success', desc: 'SHA-256 hash of input/output. Append-only Supabase table with Row Level Security.' },
  { name: 'bias_metrics', badge: 'badge-purple', desc: 'Demographic parity, disparate impact (EEOC 4/5ths), equalized odds. Flags >10% disparity.' },
  { name: 'toxicity_filter', badge: 'badge-neutral', desc: 'better-profanity + 8 healthcare-specific harm patterns. Blocks responses > 0.8 score.' },
]

const STACK = [
  { layer: 'LLM',       tool: 'Groq / Llama 3 70B', why: 'Free tier, ~300 tok/s, most capable free model', color: 'var(--color-primary)' },
  { layer: 'API',       tool: 'FastAPI + Render',    why: 'Auto-deploy from GitHub, free SSL, auto-scales', color: 'var(--color-teal)' },
  { layer: 'Database',  tool: 'Supabase PostgreSQL', why: 'Row Level Security, REST API, free tier', color: 'var(--color-success)' },
  { layer: 'NLP / PII', tool: 'Presidio + spaCy',   why: 'NLP-based PII catches what regex misses', color: 'var(--color-warning)' },
  { layer: 'Frontend',  tool: 'React + Vite + Vercel', why: 'Zero-config deploy, global CDN', color: 'var(--color-purple)' },
  { layer: 'CI/CD',     tool: 'GitHub Actions',      why: 'Free, runs on every push, includes coverage + pip-audit', color: 'var(--color-text-muted)' },
]

export default function Architecture() {
  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1>🏗️ Architecture</h1>
        <p>
          Full system design — 7-step request lifecycle, module breakdown, and the 100% free infrastructure stack.
          Built by someone who spent 13+ years inside RxClaim understanding why these guardrails matter.
        </p>
      </div>

      {/* Request lifecycle */}
      <div className="card" style={{ marginBottom: 'var(--space-5)' }}>
        <div className="card-header">
          <div className="card-title"><span className="title-icon">⚙️</span> 7-Step Request Lifecycle</div>
          <span className="badge badge-primary">Per-request pipeline</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {STEPS.map((step, i) => (
            <div key={step.id} style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'flex-start' }}>
              {/* Step number + connector */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: '50%',
                  background: `${step.color}22`, border: `2px solid ${step.color}44`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '1.1rem',
                }}>
                  {step.icon}
                </div>
                {i < STEPS.length - 1 && (
                  <div style={{ width: 2, height: 24, background: 'var(--color-border)', marginTop: 4 }} />
                )}
              </div>
              {/* Content */}
              <div style={{ flex: 1, paddingBottom: i < STEPS.length - 1 ? 'var(--space-2)' : 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>{step.id}. {step.title}</span>
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', lineHeight: 1.6 }}>{step.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Infrastructure */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)', marginBottom: 'var(--space-5)' }}>
        {/* Stack */}
        <div className="card">
          <div className="card-header">
            <div className="card-title"><span className="title-icon">🧱</span> Free Infrastructure Stack</div>
            <span className="badge badge-success">$0/month</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {STACK.map(s => (
              <div key={s.layer} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                padding: 'var(--space-3)', background: 'var(--color-surface-3)',
                borderRadius: 'var(--radius-md)', gap: 'var(--space-3)',
              }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 4 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                    <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      {s.layer}
                    </span>
                  </div>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 2 }}>{s.tool}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)' }}>{s.why}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Modules */}
        <div className="card">
          <div className="card-header">
            <div className="card-title"><span className="title-icon">📦</span> Python Modules</div>
            <span className="badge badge-teal">5 guardrails</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            {MODULES.map(m => (
              <div key={m.name} style={{
                padding: 'var(--space-3)', background: 'var(--color-surface-3)',
                borderRadius: 'var(--radius-md)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 6 }}>
                  <span className={`badge ${m.badge}`} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>
                    app/{m.name}.py
                  </span>
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', lineHeight: 1.5 }}>{m.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* HIPAA alignment */}
      <div className="card" style={{ background: 'rgba(0,212,170,0.03)', borderColor: 'rgba(0,212,170,0.2)' }}>
        <div className="card-title" style={{ marginBottom: 'var(--space-4)', color: 'var(--color-teal)' }}>
          🏥 HIPAA Security Rule Alignment
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)', fontSize: '0.85rem' }}>
          {[
            ['§164.312(b) Audit Controls', 'Every AI decision logged with user, timestamp, input hash, output hash, PII types, risk score, model, and latency.'],
            ['§164.502(b) Minimum Necessary', 'PII masking enforced BEFORE any LLM call — only masked text leaves the system boundary.'],
            ['§164.312(c) Integrity', 'Audit logs are append-only. SHA-256 hashing. Supabase RLS prevents UPDATE or DELETE.'],
            ['PHI in LLM Prompts', 'Architecturally enforced: Groq client never receives a function that accepts unmasked text.'],
          ].map(([rule, desc]) => (
            <div key={rule} style={{ padding: 'var(--space-3)', background: 'rgba(0,212,170,0.06)', borderRadius: 'var(--radius-md)', border: '1px solid rgba(0,212,170,0.15)' }}>
              <div style={{ fontWeight: 700, color: 'var(--color-teal)', marginBottom: 6, fontSize: '0.82rem' }}>{rule}</div>
              <div style={{ color: 'var(--color-text-muted)', lineHeight: 1.6, fontSize: '0.8rem' }}>{desc}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 'var(--space-4)', fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>
          ⚠️ This framework implements engineering controls. Full HIPAA compliance requires a BAA with cloud vendors, additional access controls, and legal review.
        </div>
      </div>

      {/* Interview talking points */}
      <div className="card" style={{ marginTop: 'var(--space-5)', background: 'rgba(59,158,255,0.03)' }}>
        <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>🎤 Interview Talking Points</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {[
            {
              q: 'Why did you build this?',
              a: 'After 13 years in PBM operations with RxClaim, I saw firsthand what happens when clinical data is handled carelessly in automated systems. Most AI frameworks have no concept of PHI, no audit trail, no way to flag uncertain answers. I built this to demonstrate what responsible AI looks like when you actually understand the healthcare domain.',
            },
            {
              q: 'What was the hardest technical decision?',
              a: 'The hallucination guard design. LLMs don\'t reliably self-report their own confidence. Self-consistency — running the same prompt 3 times at different temperatures and measuring agreement — is more behaviorally honest. The tradeoff is 3× Groq API calls per request, which is why HIGH-risk responses get a safe fallback instead of the AI\'s answer.',
            },
            {
              q: 'What would the production version need?',
              a: 'A BAA with Groq or a move to Azure OpenAI. Fine-tuning or RAG on actual formulary and clinical guideline documents. Role-based access control beyond API key auth. Integration with Active Directory/Okta. Performance testing under real claims volume. This framework gives you the architecture skeleton.',
            },
          ].map((item, i) => (
            <div key={i} style={{ padding: 'var(--space-4)', background: 'var(--color-surface-3)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ fontWeight: 700, color: 'var(--color-primary)', marginBottom: 8, fontSize: '0.875rem' }}>
                Q: {item.q}
              </div>
              <div style={{ color: 'var(--color-text-muted)', lineHeight: 1.7, fontSize: '0.85rem' }}>
                "{item.a}"
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

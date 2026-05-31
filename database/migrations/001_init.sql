-- ============================================================
-- Responsible AI Healthcare Framework — Supabase Migration
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- ============================================================
-- Table: audit_logs
-- Append-only audit trail for all AI decisions.
-- Maps to HIPAA Security Rule §164.312(b) Audit Controls.
-- RLS: INSERT + SELECT only. No UPDATE or DELETE = tamper-evident.
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    user_id         TEXT NOT NULL,
    context         TEXT NOT NULL,
    input_hash      TEXT NOT NULL,   -- SHA-256 of original text (never raw PHI)
    output_hash     TEXT NOT NULL,   -- SHA-256 of AI response
    pii_detected    JSONB DEFAULT '[]',
    hallucination_score  FLOAT,
    hallucination_risk   TEXT CHECK (hallucination_risk IN ('LOW', 'MEDIUM', 'HIGH')),
    toxicity_score  FLOAT,
    model_used      TEXT,
    processing_ms   INTEGER,
    masked_text     TEXT,            -- Masked version (no PHI)
    ai_response     TEXT
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id     ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at  ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_risk        ON audit_logs(hallucination_risk);

-- Row Level Security — APPEND ONLY
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "audit_allow_insert" ON audit_logs
    FOR INSERT WITH CHECK (true);

CREATE POLICY "audit_allow_select" ON audit_logs
    FOR SELECT USING (true);

-- NO UPDATE or DELETE policies → tamper-evident by construction


-- ============================================================
-- Table: pii_incidents
-- Tracks each PII detection event linked to an audit record.
-- ============================================================
CREATE TABLE IF NOT EXISTS pii_incidents (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at  TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    audit_id    UUID REFERENCES audit_logs(id) ON DELETE RESTRICT,
    pii_types   JSONB NOT NULL,
    context     TEXT
);

CREATE INDEX IF NOT EXISTS idx_pii_incidents_audit_id ON pii_incidents(audit_id);

ALTER TABLE pii_incidents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "pii_allow_insert" ON pii_incidents
    FOR INSERT WITH CHECK (true);

CREATE POLICY "pii_allow_select" ON pii_incidents
    FOR SELECT USING (true);


-- ============================================================
-- Table: bias_metrics
-- Stores periodic AI fairness reports.
-- ============================================================
CREATE TABLE IF NOT EXISTS bias_metrics (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at       TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    report_period    TEXT NOT NULL,
    demographic_group TEXT NOT NULL,
    metric_name      TEXT NOT NULL,
    metric_value     FLOAT NOT NULL,
    flagged          BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_bias_metrics_period ON bias_metrics(report_period, demographic_group);

ALTER TABLE bias_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "bias_allow_insert" ON bias_metrics
    FOR INSERT WITH CHECK (true);

CREATE POLICY "bias_allow_select" ON bias_metrics
    FOR SELECT USING (true);


-- ============================================================
-- Verification: Run this to confirm tables were created
-- ============================================================
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
-- ORDER BY table_name;

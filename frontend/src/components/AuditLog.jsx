import { useState, useEffect, useCallback } from 'react'

function RiskBadge({ risk }) {
  const map = { LOW: 'badge-success', MEDIUM: 'badge-warning', HIGH: 'badge-danger' }
  return <span className={`badge ${map[risk] || 'badge-neutral'}`}>{risk}</span>
}

function AuditDetailModal({ record, onClose }) {
  if (!record) return null
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 'var(--space-4)',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border-glow)',
          borderRadius: 'var(--radius-xl)',
          padding: 'var(--space-6)',
          maxWidth: 680,
          width: '100%',
          maxHeight: '80vh',
          overflowY: 'auto',
          boxShadow: 'var(--shadow-elevated)',
          animation: 'slideUp 0.25s ease',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-5)' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>📋 Audit Record Detail</h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: '1.2rem' }}
          >
            ✕
          </button>
        </div>

        {[
          ['Audit ID',            record.id],
          ['Timestamp',           record.created_at],
          ['User ID',             record.user_id],
          ['Context',             record.context],
          ['Model Used',          record.model_used],
          ['Processing (ms)',     record.processing_ms],
          ['PII Detected',        Array.isArray(record.pii_detected) ? record.pii_detected.join(', ') || 'None' : record.pii_detected],
          ['Hallucination Score', record.hallucination_score?.toFixed(3)],
          ['Hallucination Risk',  record.hallucination_risk],
          ['Toxicity Score',      record.toxicity_score?.toFixed(3)],
          ['Input Hash (SHA-256)',  record.input_hash],
          ['Output Hash (SHA-256)', record.output_hash],
        ].map(([label, value]) => (
          <div key={label} style={{
            display: 'grid', gridTemplateColumns: '160px 1fr',
            gap: 'var(--space-3)', marginBottom: 'var(--space-3)',
            padding: 'var(--space-3)', background: 'var(--color-surface-3)',
            borderRadius: 'var(--radius-md)', fontSize: '0.82rem',
          }}>
            <span style={{ color: 'var(--color-text-muted)', fontWeight: 600 }}>{label}</span>
            <span style={{
              fontFamily: label.includes('Hash') || label.includes('ID') ? 'var(--font-mono)' : undefined,
              color: label.includes('Hash') ? 'var(--color-teal)' : 'var(--color-text)',
              wordBreak: 'break-all',
            }}>
              {value || '—'}
            </span>
          </div>
        ))}

        {record.masked_text && (
          <div style={{ marginTop: 'var(--space-4)' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-2)' }}>
              Masked Text (Stored)
            </div>
            <div className="code-block">{record.masked_text}</div>
          </div>
        )}

        {record.ai_response && (
          <div style={{ marginTop: 'var(--space-4)' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-2)' }}>
              AI Response
            </div>
            <div style={{
              background: 'var(--color-surface-3)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-4)',
              fontSize: '0.85rem', lineHeight: 1.7, color: 'var(--color-text)',
              whiteSpace: 'pre-wrap',
            }}>
              {record.ai_response}
            </div>
          </div>
        )}

        <div style={{ marginTop: 'var(--space-5)', padding: 'var(--space-3)', background: 'var(--color-success-dim)', borderRadius: 'var(--radius-md)', fontSize: '0.78rem', color: 'var(--color-success)' }}>
          🔒 This record is append-only. HIPAA §164.312(b) — No UPDATE or DELETE permitted by Row Level Security policy.
        </div>
      </div>
    </div>
  )
}

export default function AuditLog({ apiUrl }) {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [filter, setFilter] = useState('ALL')
  const [searchId, setSearchId] = useState('')

  const fetchRecords = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${apiUrl}/api/v1/audit?limit=50`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setRecords(data.records || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [apiUrl])

  useEffect(() => { fetchRecords() }, [fetchRecords])

  const searchById = async () => {
    if (!searchId.trim()) return
    try {
      const res = await fetch(`${apiUrl}/api/v1/audit/${searchId.trim()}`)
      if (!res.ok) throw new Error('Record not found')
      const data = await res.json()
      setSelectedRecord(data)
    } catch (err) {
      alert(err.message)
    }
  }

  const filteredRecords = records.filter(r => {
    if (filter === 'ALL') return true
    return r.hallucination_risk === filter
  })

  const summary = {
    total: records.length,
    low: records.filter(r => r.hallucination_risk === 'LOW').length,
    medium: records.filter(r => r.hallucination_risk === 'MEDIUM').length,
    high: records.filter(r => r.hallucination_risk === 'HIGH').length,
    piiCaught: records.filter(r => Array.isArray(r.pii_detected) && r.pii_detected.length > 0).length,
  }

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <h1>📋 Audit Log</h1>
        <p>
          Immutable record of every AI decision. HIPAA §164.312(b) — append-only,
          tamper-evident via SHA-256 hashing and Supabase Row Level Security.
        </p>
      </div>

      {/* Stats */}
      <div className="stats-grid" style={{ marginBottom: 'var(--space-5)' }}>
        {[
          { label: 'Total Decisions', value: summary.total, icon: '📋', color: 'var(--color-primary)', dimColor: 'var(--color-primary-dim)' },
          { label: 'PII Caught', value: summary.piiCaught, icon: '🔒', color: 'var(--color-warning)', dimColor: 'var(--color-warning-dim)' },
          { label: 'LOW Risk', value: summary.low, icon: '✅', color: 'var(--color-success)', dimColor: 'var(--color-success-dim)' },
          { label: 'HIGH Risk', value: summary.high, icon: '🚨', color: 'var(--color-danger)', dimColor: 'var(--color-danger-dim)' },
        ].map(s => (
          <div key={s.label} className="stat-card" style={{ '--stat-color': s.color, '--stat-color-dim': s.dimColor }}>
            <div className="stat-icon">{s.icon}</div>
            <div className="stat-content">
              <div className="stat-label">{s.label}</div>
              <div className="stat-value">{s.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            {['ALL', 'LOW', 'MEDIUM', 'HIGH'].map(f => (
              <button
                key={f}
                className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', flex: 1, maxWidth: 420 }}>
            <input
              className="form-control"
              style={{ flex: 1 }}
              placeholder="Search by audit_id..."
              value={searchId}
              onChange={e => setSearchId(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && searchById()}
            />
            <button className="btn btn-secondary btn-sm" onClick={searchById}>Search</button>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={fetchRecords} style={{ marginLeft: 'auto' }}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0 }}>
        {loading ? (
          <div className="loading-state">
            <div className="spinner spinner-lg" />
            <div>Loading audit records...</div>
          </div>
        ) : error ? (
          <div className="empty-state">
            <div className="empty-icon">⚠️</div>
            <h3>Cannot reach API</h3>
            <p>{error}. Make sure the FastAPI server is running and the API URL is configured.</p>
            <button className="btn btn-secondary btn-sm" onClick={fetchRecords} style={{ marginTop: 'var(--space-3)' }}>
              Retry
            </button>
          </div>
        ) : filteredRecords.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <h3>No audit records yet</h3>
            <p>Run an analysis from the Analyze tab to generate your first audit log entry.</p>
          </div>
        ) : (
          <div className="table-wrap" style={{ borderRadius: 'var(--radius-lg)', border: 'none' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Audit ID</th>
                  <th>Timestamp</th>
                  <th>User</th>
                  <th>Context</th>
                  <th>PII Types</th>
                  <th>H-Score</th>
                  <th>Risk</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map(r => (
                  <tr key={r.id} onClick={() => setSelectedRecord(r)}>
                    <td>
                      <span className="mono text-primary" style={{ fontSize: '0.78rem' }}>
                        {r.id?.slice(0, 8)}...
                      </span>
                    </td>
                    <td style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                      {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                    </td>
                    <td><span className="badge badge-neutral">{r.user_id}</span></td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                      {r.context?.replace('_', ' ')}
                    </td>
                    <td>
                      {Array.isArray(r.pii_detected) && r.pii_detected.length > 0
                        ? <span className="badge badge-warning">🔒 {r.pii_detected.length} type(s)</span>
                        : <span style={{ color: 'var(--color-text-dim)', fontSize: '0.78rem' }}>None</span>
                      }
                    </td>
                    <td>
                      <span className="mono" style={{ fontSize: '0.82rem' }}>
                        {r.hallucination_score?.toFixed(2) ?? '—'}
                      </span>
                    </td>
                    <td><RiskBadge risk={r.hallucination_risk} /></td>
                    <td style={{ color: 'var(--color-text-muted)', fontSize: '0.82rem' }}>
                      {r.processing_ms ? `${r.processing_ms}ms` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedRecord && (
        <AuditDetailModal record={selectedRecord} onClose={() => setSelectedRecord(null)} />
      )}
    </div>
  )
}

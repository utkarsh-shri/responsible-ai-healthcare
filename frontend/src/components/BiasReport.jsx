import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis, Legend,
} from 'recharts'

const COLORS = {
  GroupA: '#3b9eff',
  GroupB: '#00d4aa',
  GroupC: '#a78bfa',
  GroupD: '#f59e0b',
}

const GROUP_COLORS = Object.values(COLORS)

function ComplianceBadge({ compliant }) {
  return compliant
    ? <span className="badge badge-success">✅ EEOC Compliant</span>
    : <span className="badge badge-danger">⚠️ Bias Detected</span>
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--color-surface-3)',
      border: '1px solid var(--color-border-glow)',
      borderRadius: 'var(--radius-md)',
      padding: 'var(--space-3) var(--space-4)',
      fontSize: '0.82rem',
    }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.fill || p.color, marginBottom: 2 }}>
          {p.name}: {(p.value * 100).toFixed(1)}%
        </div>
      ))}
    </div>
  )
}

export default function BiasReport({ apiUrl }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchReport = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${apiUrl}/api/v1/bias-report`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchReport() }, [])

  if (loading) return (
    <div className="loading-state">
      <div className="spinner spinner-lg" />
      <div>Computing fairness metrics...</div>
    </div>
  )

  if (error) return (
    <div className="empty-state">
      <div className="empty-icon">⚠️</div>
      <h3>Cannot load bias report</h3>
      <p>{error}</p>
      <button className="btn btn-secondary btn-sm" onClick={fetchReport} style={{ marginTop: 'var(--space-3)' }}>
        Retry
      </button>
    </div>
  )

  const chartData = data?.metrics?.map(m => ({
    name: m.demographic_group,
    approval_rate: m.metric_value,
    flagged: m.flagged,
  })) || []

  const radarData = data?.metrics?.map(m => ({
    group: m.demographic_group,
    'Approval Rate': m.metric_value,
    'Baseline': 0.8,
  })) || []

  const dpPct = ((data?.demographic_parity_difference || 0) * 100).toFixed(1)
  const diRatio = (data?.disparate_impact_ratio || 0).toFixed(3)
  const diPass = (data?.disparate_impact_ratio || 0) >= 0.8

  return (
    <div className="animate-fade-in">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
          <div>
            <h1>⚖️ Bias & Fairness Report</h1>
            <p>
              AI prediction fairness across demographic groups.
              Thresholds: EEOC 4/5ths rule (DI ≥ 0.80) · 10% disparity flag.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <ComplianceBadge compliant={data?.compliant} />
            <button className="btn btn-secondary btn-sm" onClick={fetchReport}>↻ Refresh</button>
          </div>
        </div>
      </div>

      {/* Key metrics */}
      <div className="stats-grid" style={{ marginBottom: 'var(--space-5)' }}>
        {[
          {
            label: 'Total Predictions',
            value: data?.total_predictions || 0,
            icon: '📊',
            color: 'var(--color-primary)',
            dimColor: 'var(--color-primary-dim)',
            desc: `Across ${data?.metrics?.length || 0} demographic groups`,
          },
          {
            label: 'Demographic Parity Diff',
            value: `${dpPct}%`,
            icon: dpPct > 10 ? '⚠️' : '✅',
            color: dpPct > 10 ? 'var(--color-danger)' : 'var(--color-success)',
            dimColor: dpPct > 10 ? 'var(--color-danger-dim)' : 'var(--color-success-dim)',
            desc: `Threshold: ≤ 10%`,
          },
          {
            label: 'Disparate Impact Ratio',
            value: diRatio,
            icon: diPass ? '✅' : '🚨',
            color: diPass ? 'var(--color-success)' : 'var(--color-danger)',
            dimColor: diPass ? 'var(--color-success-dim)' : 'var(--color-danger-dim)',
            desc: `EEOC 4/5ths rule: ≥ 0.80`,
          },
          {
            label: 'Flagged Groups',
            value: data?.flagged_groups?.length || 0,
            icon: '🚩',
            color: data?.flagged_groups?.length > 0 ? 'var(--color-warning)' : 'var(--color-success)',
            dimColor: data?.flagged_groups?.length > 0 ? 'var(--color-warning-dim)' : 'var(--color-success-dim)',
            desc: data?.flagged_groups?.length > 0 ? `Groups: ${data.flagged_groups.join(', ')}` : 'No groups flagged',
          },
        ].map(s => (
          <div key={s.label} className="stat-card" style={{ '--stat-color': s.color, '--stat-color-dim': s.dimColor }}>
            <div className="stat-icon">{s.icon}</div>
            <div className="stat-content">
              <div className="stat-label">{s.label}</div>
              <div className="stat-value" style={{ fontSize: '1.4rem' }}>{s.value}</div>
              <div className="stat-desc">{s.desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Flagged groups alert */}
      {data?.flagged_groups?.length > 0 && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--space-5)' }}>
          <span style={{ fontSize: '1.2rem' }}>⚠️</span>
          <div>
            <strong>Bias Detected:</strong> Group(s) {data.flagged_groups.join(', ')} show{data.flagged_groups.length > 1 ? '' : 's'} {'>'} 10%
            worse approval rates than the best-performing group.
            Recommend review of training data and model outputs for systematic disparities.
          </div>
        </div>
      )}

      {!data?.compliant || data?.flagged_groups?.length === 0 ? null : null}
      {data?.compliant && data?.flagged_groups?.length === 0 && (
        <div className="alert alert-success" style={{ marginBottom: 'var(--space-5)' }}>
          ✅ No significant bias detected across all demographic groups. EEOC 4/5ths rule: PASS.
        </div>
      )}

      {/* Charts */}
      <div className="bias-grid">
        {/* Bar chart — approval rates */}
        <div className="card">
          <div className="card-header">
            <div className="card-title"><span className="title-icon">📊</span> Approval Rates by Group</div>
            <span className="badge badge-neutral">Demographic Parity</span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,179,237,0.1)" />
              <XAxis dataKey="name" tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }} />
              <YAxis
                tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                domain={[0, 1]}
                tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="approval_rate" name="Approval Rate" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.flagged ? 'var(--color-danger)' : GROUP_COLORS[i % GROUP_COLORS.length]}
                    opacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', marginTop: 'var(--space-3)' }}>
            {chartData.map((g, i) => (
              <div key={g.name} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem' }}>
                <div style={{
                  width: 10, height: 10, borderRadius: 2,
                  background: g.flagged ? 'var(--color-danger)' : GROUP_COLORS[i % GROUP_COLORS.length],
                }} />
                <span style={{ color: 'var(--color-text-muted)' }}>{g.name}</span>
                <span style={{ color: 'var(--color-text)', fontWeight: 600 }}>
                  {(g.approval_rate * 100).toFixed(1)}%
                </span>
                {g.flagged && <span className="badge badge-danger" style={{ padding: '1px 6px', fontSize: '0.65rem' }}>FLAGGED</span>}
              </div>
            ))}
          </div>
        </div>

        {/* Compliance gauges */}
        <div className="card">
          <div className="card-header">
            <div className="card-title"><span className="title-icon">🎯</span> Compliance Thresholds</div>
            <ComplianceBadge compliant={data?.compliant} />
          </div>

          {/* Disparate Impact */}
          <div style={{ marginBottom: 'var(--space-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)', fontSize: '0.85rem' }}>
              <span style={{ fontWeight: 600 }}>Disparate Impact Ratio</span>
              <span className={`badge ${diPass ? 'badge-success' : 'badge-danger'}`}>
                {diPass ? 'PASS' : 'FAIL'}
              </span>
            </div>
            <div style={{ height: 10, background: 'var(--color-surface-3)', borderRadius: 'var(--radius-full)', overflow: 'hidden', position: 'relative' }}>
              <div style={{
                height: '100%', width: `${Math.min(data?.disparate_impact_ratio * 100, 100)}%`,
                background: diPass ? 'var(--color-success)' : 'var(--color-danger)',
                borderRadius: 'var(--radius-full)',
                transition: 'width 1s ease',
              }} />
              {/* 80% threshold marker */}
              <div style={{
                position: 'absolute', top: 0, bottom: 0, left: '80%',
                width: 2, background: 'var(--color-warning)',
              }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 6 }}>
              <span>0.00</span>
              <span style={{ color: 'var(--color-warning)' }}>← 0.80 threshold</span>
              <span>1.00</span>
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', marginTop: 8 }}>
              Computed ratio: <strong style={{ color: 'var(--color-text)' }}>{diRatio}</strong> ·
              EEOC 4/5ths rule: min_rate / max_rate ≥ 0.80
            </div>
          </div>

          <div className="divider" />

          {/* Demographic Parity */}
          <div style={{ marginBottom: 'var(--space-5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)', fontSize: '0.85rem' }}>
              <span style={{ fontWeight: 600 }}>Demographic Parity Difference</span>
              <span className={`badge ${dpPct <= 10 ? 'badge-success' : 'badge-danger'}`}>
                {dpPct <= 10 ? 'PASS' : 'FAIL'}
              </span>
            </div>
            <div style={{ height: 10, background: 'var(--color-surface-3)', borderRadius: 'var(--radius-full)', overflow: 'hidden', position: 'relative' }}>
              <div style={{
                height: '100%', width: `${Math.min(dpPct, 100)}%`,
                background: dpPct <= 10 ? 'var(--color-success)' : 'var(--color-danger)',
                borderRadius: 'var(--radius-full)',
                transition: 'width 1s ease',
              }} />
              <div style={{ position: 'absolute', top: 0, bottom: 0, left: '10%', width: 2, background: 'var(--color-warning)' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 6 }}>
              <span>0%</span>
              <span style={{ color: 'var(--color-warning)' }}>← 10% threshold</span>
              <span>100%</span>
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--color-text-muted)', marginTop: 8 }}>
              Computed difference: <strong style={{ color: 'var(--color-text)' }}>{dpPct}%</strong> ·
              max_rate − min_rate across all groups
            </div>
          </div>

          <div className="divider" />

          {/* Group breakdown */}
          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 'var(--space-3)' }}>
              Group Breakdown
            </div>
            <div className="metric-gauge">
              {chartData.sort((a, b) => b.approval_rate - a.approval_rate).map((g, i) => (
                <div key={g.name} className="gauge-row">
                  <span className="gauge-label">{g.name}</span>
                  <div className="gauge-bar">
                    <div
                      className="gauge-fill"
                      style={{
                        width: `${g.approval_rate * 100}%`,
                        background: g.flagged ? 'var(--color-danger)' : GROUP_COLORS[i % GROUP_COLORS.length],
                      }}
                    />
                  </div>
                  <span className="gauge-pct">{(g.approval_rate * 100).toFixed(1)}%</span>
                  {g.flagged && <span className="badge badge-danger" style={{ padding: '1px 6px', fontSize: '0.65rem' }}>⚠️</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Methodology note */}
      <div className="card" style={{ marginTop: 'var(--space-5)', background: 'rgba(59,158,255,0.03)' }}>
        <div className="card-title" style={{ marginBottom: 'var(--space-3)' }}>📖 Methodology</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-4)', fontSize: '0.82rem', color: 'var(--color-text-muted)' }}>
          {[
            ['Demographic Parity', 'max(P(ŷ=1|A)) − min(P(ŷ=1|A)) across all groups. Measures equal approval rates. Threshold: ≤ 10%.'],
            ['Disparate Impact', 'min_rate / max_rate. Based on EEOC 4/5ths rule. Values < 0.80 indicate adverse impact on the lower-performing group.'],
            ['Equalized Odds', 'Difference in True Positive Rate across groups. Requires ground truth labels. Measures equal accuracy, not just equal rates.'],
          ].map(([title, desc]) => (
            <div key={title}>
              <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>{title}</div>
              {desc}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

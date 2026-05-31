import { useState, useCallback } from 'react'
import AnalyzePanel from './components/AnalyzePanel'
import AuditLog from './components/AuditLog'
import BiasReport from './components/BiasReport'
import Architecture from './components/Architecture'

const API_URL = import.meta.env.VITE_API_URL || ''

const TABS = [
  { id: 'analyze',  label: 'Analyze', icon: '🔬' },
  { id: 'audit',    label: 'Audit Log', icon: '📋' },
  { id: 'bias',     label: 'Bias Report', icon: '⚖️' },
  { id: 'architecture', label: 'Architecture', icon: '🏗️' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('analyze')
  const [apiStatus, setApiStatus] = useState(null) // null | 'ok' | 'error'

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/health`)
      const data = await res.json()
      setApiStatus(data.status === 'ok' || data.status === 'degraded' ? 'ok' : 'error')
    } catch {
      setApiStatus('error')
    }
  }, [])

  // Check health on mount
  useState(() => { checkHealth() }, [])

  return (
    <div className="app">
      {/* Top bar */}
      <header className="topbar">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div style={{
              width: 32, height: 32,
              background: 'linear-gradient(135deg, var(--color-primary), var(--color-teal))',
              borderRadius: 8,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, flexShrink: 0
            }}>🛡️</div>
            <div>
              <div className="topbar-title">
                Responsible <span>AI Healthcare</span>
              </div>
              <div style={{ fontSize: '0.68rem', color: 'var(--color-text-muted)', lineHeight: 1 }}>
                Utkarsh Shrivastava · 13+ yrs PBM / RxClaim / CMS
              </div>
            </div>
          </div>
        </div>
        <div className="topbar-badges flex items-center gap-2">
          <span className="badge badge-teal">HIPAA-aligned</span>
          <span className="badge badge-primary">PII Masking</span>
          <span className="badge badge-purple">Hallucination Guard</span>
          <div
            className="badge"
            style={{
              background: apiStatus === 'ok' ? 'var(--color-success-dim)' : apiStatus === 'error' ? 'var(--color-danger-dim)' : 'var(--color-surface-3)',
              color: apiStatus === 'ok' ? 'var(--color-success)' : apiStatus === 'error' ? 'var(--color-danger)' : 'var(--color-text-muted)',
              border: '1px solid',
              borderColor: apiStatus === 'ok' ? 'rgba(34,197,94,0.3)' : apiStatus === 'error' ? 'rgba(239,68,68,0.3)' : 'var(--color-border)',
              cursor: 'pointer',
            }}
            onClick={checkHealth}
            title="Click to refresh API status"
          >
            <span style={{ fontSize: 8 }}>●</span>
            {apiStatus === 'ok' ? 'API Online' : apiStatus === 'error' ? 'API Offline' : 'Checking...'}
          </div>
        </div>
      </header>

      <div className="app-layout">
        {/* Sidebar */}
        <nav className="sidebar">
          <div className="sidebar-logo">
            <h2>
              <span className="logo-icon">🛡️</span>
              RAI Healthcare
            </h2>
            <p>Responsible AI Framework v1.0</p>
          </div>
          <div className="sidebar-nav">
            {TABS.map(tab => (
              <button
                key={tab.id}
                className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                <span className="nav-icon">{tab.icon}</span>
                {tab.label}
              </button>
            ))}
          </div>
          <div className="sidebar-footer">
            <div style={{ marginBottom: 6 }}>
              <a href="https://github.com/utkarsh-shri/responsible-ai-healthcare" target="_blank" rel="noopener">
                GitHub ↗
              </a>
              {' · '}
              <a href="https://linkedin.com/in/utkarsh-shrivastava" target="_blank" rel="noopener">
                LinkedIn ↗
              </a>
            </div>
            <div>Stack: FastAPI · Groq · Supabase · React</div>
            <div style={{ marginTop: 4, color: 'var(--color-text-dim)' }}>$0/month infrastructure</div>
          </div>
        </nav>

        {/* Main content */}
        <main className="main-content">
          {activeTab === 'analyze'      && <AnalyzePanel apiUrl={API_URL} />}
          {activeTab === 'audit'        && <AuditLog apiUrl={API_URL} />}
          {activeTab === 'bias'         && <BiasReport apiUrl={API_URL} />}
          {activeTab === 'architecture' && <Architecture />}
        </main>
      </div>
    </div>
  )
}

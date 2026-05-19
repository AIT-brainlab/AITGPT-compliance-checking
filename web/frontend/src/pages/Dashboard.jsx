import { useState, useEffect } from 'react'
import { ChevronDown, FileText, Brain, Shapes, AlertTriangle } from 'lucide-react'

const FUNNEL_STEPS = [
  { label: 'Sentences Extracted', key: 'sentences_extracted', color: '#e0e7ff', width: '100%' },
  { label: 'Candidates (Pre-filter)', key: 'candidates_prefiltered', color: '#c7d2fe', width: '82%' },
  { label: 'Rules Classified', key: 'total_rules', color: '#a5b4fc', width: '74%' },
  { label: 'FOL Formulas', key: 'fol_ok', color: '#818cf8', width: '60%' },
  { label: 'Valid SHACL Shapes', key: 'shapes_valid', color: '#6366f1', width: '52%', textLight: true },
]

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/stats')
      .then(r => r.json())
      .then(data => { setStats(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center mt-4"><div className="spinner" style={{ margin: '40px auto' }} /></div>
  if (!stats) return <p className="text-muted">Failed to load pipeline data.</p>

  const dist = stats.type_distribution || {}

  return (
    <>
      <div className="page-header">
        <h2>Pipeline Dashboard</h2>
        <p>Overview of the automated policy formalization pipeline — AIT corpus</p>
      </div>

      {/* Stats cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Rules</div>
          <div className="stat-value">{stats.total_rules}</div>
          <div className="stat-sub">Classified by Mistral 7B</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">FOL Formulas</div>
          <div className="stat-value">{stats.fol_ok}</div>
          <div className="stat-sub">{stats.fol_failed} routed to NL fallback</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Valid Shapes</div>
          <div className="stat-value">{stats.shapes_valid}</div>
          <div className="stat-sub">of {stats.shapes_total} generated</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Pipeline</div>
          <div className="stat-value" style={{ fontSize: '1rem' }}>{stats.pipeline_version}</div>
          <div className="stat-sub">Frozen snapshot</div>
        </div>
      </div>

      <div className="grid-2">
        {/* Pipeline Funnel */}
        <div className="card">
          <div className="card-header">
            <span>Pipeline Funnel</span>
            <FileText size={16} style={{ color: 'var(--text-muted)' }} />
          </div>
          <div className="funnel">
            {FUNNEL_STEPS.map((step, i) => (
              <div key={step.key}>
                <div
                  className="funnel-step"
                  style={{
                    background: step.color,
                    width: step.width,
                    minWidth: '260px',
                    color: step.textLight ? '#fff' : 'var(--text-primary)',
                  }}
                >
                  <span>{step.label}: <strong>{stats[step.key] ?? '—'}</strong></span>
                </div>
                {i < FUNNEL_STEPS.length - 1 && (
                  <div className="funnel-arrow text-center">
                    <ChevronDown size={18} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Type Distribution */}
        <div className="card">
          <div className="card-header">
            <span>Rule Type Distribution</span>
            <Brain size={16} style={{ color: 'var(--text-muted)' }} />
          </div>
          <div className="card-body">
            {Object.entries(dist).map(([type, count]) => {
              const total = Object.values(dist).reduce((a, b) => a + b, 0)
              const pct = ((count / total) * 100).toFixed(1)
              const colors = {
                obligation: 'var(--obligation)',
                permission: 'var(--permission)',
                prohibition: 'var(--prohibition)',
                exemption: 'var(--exemption)',
              }
              return (
                <div key={type} style={{ marginBottom: '14px' }}>
                  <div className="flex justify-between items-center mb-3" style={{ marginBottom: '4px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.85rem', textTransform: 'capitalize' }}>{type}</span>
                    <span className="text-xs text-muted">{count} ({pct}%)</span>
                  </div>
                  <div style={{
                    height: '8px',
                    background: 'var(--bg-code)',
                    borderRadius: '4px',
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%',
                      width: `${pct}%`,
                      background: colors[type] || 'var(--accent)',
                      borderRadius: '4px',
                      transition: 'width 0.6s ease',
                    }} />
                  </div>
                </div>
              )
            })}

            <div style={{ marginTop: '24px', padding: '14px', background: 'var(--bg-code)', borderRadius: 'var(--radius-sm)' }}>
              <div className="text-xs text-muted" style={{ marginBottom: '8px', fontWeight: 600 }}>KEY METRICS</div>
              <div className="flex gap-4" style={{ flexWrap: 'wrap' }}>
                <div><span className="text-xs text-muted">IRR Fleiss' κ</span><br /><strong>0.8436</strong></div>
                <div><span className="text-xs text-muted">LLM Accuracy</span><br /><strong>84.0%</strong></div>
                <div><span className="text-xs text-muted">M3 FOL Quality</span><br /><strong>100%</strong></div>
                <div><span className="text-xs text-muted">M5 Stability</span><br /><strong>PASS</strong></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

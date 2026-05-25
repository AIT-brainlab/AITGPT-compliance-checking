import { useState, useEffect } from 'react'
import { Database, ShieldCheck, AlertTriangle, CheckCircle, Loader, ChevronDown, ChevronUp, Lightbulb, XCircle, Info } from 'lucide-react'
import Badge from '../components/Badge'

export default function Validate() {
  const [dbStatus, setDbStatus] = useState(null)
  const [entities, setEntities] = useState([])
  const [selectedEntities, setSelectedEntities] = useState(new Set())
  const [turtleData, setTurtleData] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingDb, setLoadingDb] = useState(false)
  const [validating, setValidating] = useState(false)
  const [expandedEntity, setExpandedEntity] = useState(null)
  const [filterType, setFilterType] = useState('all')

  useEffect(() => {
    fetch('/api/db-status')
      .then(r => r.json())
      .then(data => setDbStatus(data))
      .catch(() => setDbStatus({ ok: false, error: 'Cannot reach API' }))
  }, [])

  useEffect(() => {
    if (dbStatus?.ok) {
      fetch('/api/db-entities')
        .then(r => r.json())
        .then(data => setEntities(data.entities || []))
        .catch(() => {})
    }
  }, [dbStatus])

  const toggleEntity = (name) => {
    setSelectedEntities(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  const selectAll = () => {
    if (selectedEntities.size === filteredEntities.length) {
      setSelectedEntities(new Set())
    } else {
      setSelectedEntities(new Set(filteredEntities.map(e => e.name)))
    }
  }

  const loadFromDb = async () => {
    setLoadingDb(true)
    try {
      const body = selectedEntities.size > 0
        ? { entities: [...selectedEntities] }
        : { entities: 'all' }
      const res = await fetch('/api/load-from-db', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (data.turtle) setTurtleData(data.turtle)
    } catch (err) {
      console.error('Failed to load from DB:', err)
    }
    setLoadingDb(false)
  }

  const runValidation = async () => {
    if (!turtleData.trim()) return
    setValidating(true)
    setResults(null)
    try {
      const res = await fetch('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: turtleData, shapes: 'all' }),
      })
      const data = await res.json()
      setResults(data)
    } catch (err) {
      setResults({ error: err.message })
    }
    setValidating(false)
  }

  // Filter entities by type
  const filteredEntities = filterType === 'all'
    ? entities
    : entities.filter(e => e.type === filterType)

  const entityTypes = [...new Set(entities.map(e => e.type))]

  // Group violations by entity
  const groupedViolations = results?.violations?.reduce((acc, v) => {
    const key = v.focus_node || 'Unknown'
    if (!acc[key]) acc[key] = { violations: [], info: [] }
    if (v.severity === 'Info') {
      acc[key].info.push(v)
    } else {
      acc[key].violations.push(v)
    }
    return acc
  }, {}) || {}

  // Compliance summary
  const totalEntities = results?.total_entities || 0
  const entitiesWithViolations = Object.keys(groupedViolations).filter(
    k => groupedViolations[k].violations.length > 0
  ).length
  const compliantEntities = totalEntities - entitiesWithViolations
  const violationCount = results?.violations?.filter(v => v.severity === 'Violation').length || 0
  const infoCount = results?.violations?.filter(v => v.severity === 'Info').length || 0

  return (
    <>
      <div className="page-header">
        <h2>Compliance Validator</h2>
        <p>Select entities from the database, convert to RDF, and validate against 443 generated SHACL policy shapes</p>
      </div>

      {/* Stats */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="stat-card">
          <div className="stat-label">Database</div>
          <div className="stat-value" style={{ fontSize: '1rem', color: dbStatus?.ok ? 'var(--success)' : 'var(--danger)' }}>
            {dbStatus?.ok ? '● Connected' : '● Disconnected'}
          </div>
          <div className="stat-sub">{dbStatus?.ok ? 'PostgreSQL ready' : dbStatus?.error || 'Loading...'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Entities</div>
          <div className="stat-value">{entities.length}</div>
          <div className="stat-sub">{selectedEntities.size} selected</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Compliance</div>
          <div className="stat-value" style={{ fontSize: '1rem', color: results ? (results.conforms ? 'var(--success)' : 'var(--danger)') : 'var(--text-muted)' }}>
            {results ? (results.conforms ? '✓ All Conform' : `${compliantEntities}/${totalEntities} pass`) : '—'}
          </div>
          <div className="stat-sub">{results ? `${violationCount} violations, ${infoCount} info` : 'Not run yet'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Violations</div>
          <div className="stat-value" style={{ color: violationCount > 0 ? 'var(--danger)' : 'var(--success)' }}>
            {results ? violationCount : '—'}
          </div>
          <div className="stat-sub">{results ? `${entitiesWithViolations} entities affected` : ''}</div>
        </div>
      </div>

      <div className="grid-2">
        {/* Left: Entity selection + RDF */}
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-header">
              <span><Database size={16} style={{ marginRight: '8px', verticalAlign: 'text-bottom' }} />Entity Selector</span>
              <div className="flex gap-2">
                <select
                  className="input"
                  style={{ width: 'auto', padding: '4px 8px', fontSize: '0.8rem' }}
                  value={filterType}
                  onChange={e => setFilterType(e.target.value)}
                >
                  <option value="all">All Types</option>
                  {entityTypes.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <button className="btn btn-outline btn-sm" onClick={selectAll}>
                  {selectedEntities.size === filteredEntities.length ? 'Deselect All' : 'Select All'}
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={loadFromDb}
                  disabled={loadingDb || !dbStatus?.ok}
                >
                  {loadingDb ? <><Loader size={14} className="spinner" /> Loading...</> : 'Load from DB'}
                </button>
              </div>
            </div>
            <div className="card-body">
              {!dbStatus?.ok ? (
                <p className="text-muted text-sm">Database not connected. Start PostgreSQL to load entities.</p>
              ) : entities.length === 0 ? (
                <p className="text-muted text-sm">No entities found. Run <code>python -m db.seed</code> to populate.</p>
              ) : (
                <div className="entity-list" style={{ maxHeight: '350px', overflowY: 'auto' }}>
                  {filteredEntities.map(entity => (
                    <label
                      key={entity.name}
                      className={`entity-item ${selectedEntities.has(entity.name) ? 'selected' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedEntities.has(entity.name)}
                        onChange={() => toggleEntity(entity.name)}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {entity.name}
                          <span className="badge" style={{
                            fontSize: '0.65rem',
                            padding: '1px 6px',
                            background: entity.type === 'Student' || entity.type === 'PostgraduateStudent'
                              ? 'var(--primary-light)' : entity.type === 'Faculty'
                              ? '#e8f5e9' : entity.type === 'Employee' ? '#fff3e0' : '#f3e5f5',
                            color: entity.type === 'Student' || entity.type === 'PostgraduateStudent'
                              ? 'var(--primary)' : entity.type === 'Faculty'
                              ? '#2e7d32' : entity.type === 'Employee' ? '#e65100' : '#7b1fa2',
                            borderRadius: '4px',
                          }}>{entity.type}</span>
                          {entity.issues > 0 && (
                            <span style={{ color: 'var(--danger)', fontSize: '0.7rem', fontWeight: 500 }}>
                              ⚠ {entity.issues} issue{entity.issues > 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                        <div className="entity-type" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {entity.detail}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* RDF Preview */}
          <div className="card">
            <div className="card-header">
              <span>RDF Data (Turtle)</span>
              <span className="text-xs text-muted">{turtleData ? `${turtleData.split('\n').length} lines` : 'Empty'}</span>
            </div>
            <div className="card-body">
              <textarea
                className="input"
                value={turtleData}
                onChange={e => setTurtleData(e.target.value)}
                placeholder="Load from database or paste RDF Turtle data here..."
                style={{ minHeight: '180px', fontFamily: 'JetBrains Mono, monospace', fontSize: '0.75rem' }}
              />
              <div className="mt-3 flex gap-2">
                <button
                  className="btn btn-primary"
                  onClick={runValidation}
                  disabled={validating || !turtleData.trim()}
                >
                  {validating ? <><div className="spinner" /> Validating...</> : <><ShieldCheck size={16} /> Run Validation</>}
                </button>
                {turtleData && (
                  <button className="btn btn-outline" onClick={() => { setTurtleData(''); setResults(null) }}>
                    Clear
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right: Results */}
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-header">
              <span>Validation Report</span>
              {results && (
                <Badge type={results.conforms ? 'success' : 'violation'}>
                  {results.conforms ? 'ALL CONFORM' : 'NON-CONFORMANT'}
                </Badge>
              )}
            </div>
            <div className="card-body">
              {!results ? (
                <div className="text-center text-muted" style={{ padding: '60px 20px' }}>
                  <ShieldCheck size={48} style={{ opacity: 0.2, marginBottom: '12px' }} />
                  <p>Load entities and run validation to see results</p>
                </div>
              ) : results.error ? (
                <div style={{ color: 'var(--danger)', padding: '20px' }}>
                  <AlertTriangle size={20} /> Error: {results.error}
                </div>
              ) : results.conforms ? (
                <div style={{ padding: '40px', textAlign: 'center', background: '#f0fdf4', borderRadius: '8px' }}>
                  <CheckCircle size={48} style={{ color: 'var(--success)', marginBottom: '12px' }} />
                  <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--success)' }}>All Entities Conform</div>
                  <div className="text-sm mt-2" style={{ color: '#4a5568' }}>{totalEntities} entities validated against 443 policy shapes</div>
                </div>
              ) : (
                <div style={{ maxHeight: '700px', overflowY: 'auto' }}>
                  {/* Compliance summary bar */}
                  <div style={{
                    display: 'flex', gap: '8px', marginBottom: '16px', padding: '12px',
                    background: '#f7fafc', borderRadius: '8px', alignItems: 'center',
                  }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', height: '8px', borderRadius: '4px', overflow: 'hidden', background: '#e2e8f0' }}>
                        {compliantEntities > 0 && (
                          <div style={{
                            width: `${(compliantEntities / totalEntities) * 100}%`,
                            background: 'var(--success)',
                          }} />
                        )}
                        {entitiesWithViolations > 0 && (
                          <div style={{
                            width: `${(entitiesWithViolations / totalEntities) * 100}%`,
                            background: 'var(--danger)',
                          }} />
                        )}
                      </div>
                      <div className="text-xs mt-1" style={{ color: '#718096' }}>
                        <span style={{ color: 'var(--success)' }}>■</span> {compliantEntities} compliant
                        {' · '}
                        <span style={{ color: 'var(--danger)' }}>■</span> {entitiesWithViolations} non-compliant
                      </div>
                    </div>
                  </div>

                  {/* Per-entity results */}
                  {Object.entries(groupedViolations).map(([entity, { violations, info }]) => {
                    const isExpanded = expandedEntity === entity
                    const hasViolations = violations.length > 0
                    return (
                      <div key={entity} style={{
                        marginBottom: '8px', border: '1px solid #e2e8f0',
                        borderRadius: '8px', overflow: 'hidden',
                        borderLeft: `3px solid ${hasViolations ? 'var(--danger)' : 'var(--success)'}`,
                      }}>
                        <div
                          onClick={() => setExpandedEntity(isExpanded ? null : entity)}
                          style={{
                            padding: '10px 14px', cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: '10px',
                            background: isExpanded ? '#f7fafc' : 'white',
                          }}
                        >
                          {hasViolations
                            ? <XCircle size={18} style={{ color: 'var(--danger)', flexShrink: 0 }} />
                            : <CheckCircle size={18} style={{ color: 'var(--success)', flexShrink: 0 }} />
                          }
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 700, fontSize: '0.87rem' }}>{entity}</div>
                            <div style={{ fontSize: '0.73rem', color: '#718096' }}>
                              {hasViolations
                                ? `${violations.length} violation${violations.length > 1 ? 's' : ''}${info.length > 0 ? `, ${info.length} info` : ''}`
                                : info.length > 0 ? `${info.length} info notices` : 'Fully compliant'
                              }
                            </div>
                          </div>
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </div>

                        {isExpanded && (
                          <div style={{ padding: '0 14px 14px' }}>
                            {violations.map((v, i) => (
                              <div key={i} style={{
                                padding: '10px 12px', marginTop: '8px',
                                background: '#fff5f5', borderRadius: '6px',
                                borderLeft: '3px solid var(--danger)',
                              }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                                  <AlertTriangle size={13} style={{ color: 'var(--danger)' }} />
                                  <span style={{ fontWeight: 600, fontSize: '0.8rem' }}>{v.source_shape}</span>
                                  <span style={{ fontSize: '0.7rem', color: '#a0aec0' }}>sh:path {v.path}</span>
                                </div>
                                {v.message && (
                                  <div style={{ fontSize: '0.75rem', color: '#4a5568', lineHeight: '1.5', marginBottom: '6px' }}>
                                    {v.message.slice(0, 200)}
                                  </div>
                                )}
                                {v.suggestion && (
                                  <div style={{
                                    display: 'flex', alignItems: 'flex-start', gap: '6px',
                                    padding: '6px 8px', background: '#fffbeb', borderRadius: '4px',
                                    fontSize: '0.73rem', color: '#92400e',
                                  }}>
                                    <Lightbulb size={13} style={{ flexShrink: 0, marginTop: '1px' }} />
                                    <span><strong>Action:</strong> {v.suggestion}</span>
                                  </div>
                                )}
                              </div>
                            ))}
                            {info.map((v, i) => (
                              <div key={`info-${i}`} style={{
                                padding: '8px 12px', marginTop: '6px',
                                background: '#ebf8ff', borderRadius: '6px',
                                borderLeft: '3px solid #3182ce',
                              }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  <Info size={13} style={{ color: '#3182ce' }} />
                                  <span style={{ fontWeight: 600, fontSize: '0.78rem' }}>{v.source_shape}</span>
                                </div>
                                {v.message && (
                                  <div style={{ fontSize: '0.73rem', color: '#4a5568', marginTop: '2px' }}>
                                    {v.message.slice(0, 150)}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

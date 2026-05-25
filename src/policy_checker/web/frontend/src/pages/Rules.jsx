import { useState, useEffect, useCallback } from 'react'
import { Search, X } from 'lucide-react'
import Badge from '../components/Badge'

export default function Rules() {
  const [rules, setRules] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchRules = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams({ page, per_page: 20 })
    if (typeFilter !== 'all') params.set('rule_type', typeFilter)
    if (search) params.set('search', search)
    fetch(`/api/rules?${params}`)
      .then(r => r.json())
      .then(data => {
        setRules(data.rules)
        setTotal(data.total)
        setTotalPages(data.total_pages)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [page, search, typeFilter])

  useEffect(() => { fetchRules() }, [fetchRules])

  const selectRule = (ruleId) => {
    setSelected(ruleId)
    fetch(`/api/rules/${ruleId}`)
      .then(r => r.json())
      .then(data => setDetail(data))
  }

  return (
    <>
      <div className="page-header">
        <h2>Policy Rules</h2>
        <p>{total} rules extracted from AIT Policies & Procedures documents</p>
      </div>

      {/* Search & Filter */}
      <div className="search-bar">
        <div style={{ position: 'relative', flex: 1, maxWidth: '400px' }}>
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '11px', color: 'var(--text-muted)' }} />
          <input
            className="input"
            style={{ paddingLeft: '36px' }}
            placeholder="Search rules by text, ID, or document..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
        </div>
        <select className="select" value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1) }}>
          <option value="all">All Types</option>
          <option value="obligation">Obligation</option>
          <option value="permission">Permission</option>
          <option value="prohibition">Prohibition</option>
          <option value="exemption">Exemption</option>
        </select>
        {(search || typeFilter !== 'all') && (
          <button className="btn btn-outline btn-sm" onClick={() => { setSearch(''); setTypeFilter('all'); setPage(1) }}>
            <X size={14} /> Clear
          </button>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 420px' : '1fr', gap: '20px' }}>
        {/* Rules table */}
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '90px' }}>ID</th>
                <th>Rule Text</th>
                <th style={{ width: '100px' }}>Type</th>
                <th style={{ width: '80px' }}>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="text-center text-muted" style={{ padding: '40px' }}>
                  <div className="spinner" style={{ margin: '0 auto' }} />
                </td></tr>
              ) : rules.length === 0 ? (
                <tr><td colSpan={4} className="text-center text-muted" style={{ padding: '40px' }}>
                  No rules found
                </td></tr>
              ) : rules.map(rule => (
                <tr
                  key={rule.rule_id}
                  onClick={() => selectRule(rule.rule_id)}
                  style={selected === rule.rule_id ? { background: 'var(--accent-light)' } : {}}
                >
                  <td>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', fontWeight: 600 }}>
                      {rule.rule_id}
                    </span>
                  </td>
                  <td style={{ maxWidth: '500px', lineHeight: '1.5' }}>
                    {rule.text?.length > 160 ? rule.text.slice(0, 160) + '…' : rule.text}
                  </td>
                  <td><Badge type={rule.rule_type} /></td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {(rule.confidence * 100).toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          <div className="pagination">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span>Page {page} of {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        </div>

        {/* Detail panel */}
        {selected && detail && (
          <div className="detail-panel" style={{ position: 'sticky', top: '20px', alignSelf: 'start' }}>
            <div className="card-header">
              <span>{detail.rule?.rule_id}</span>
              <button className="btn btn-outline btn-sm" onClick={() => { setSelected(null); setDetail(null) }}>
                <X size={14} />
              </button>
            </div>

            <div className="detail-section">
              <h4>Natural Language</h4>
              <p style={{ fontSize: '0.85rem', lineHeight: '1.6' }}>{detail.rule?.text}</p>
              <div className="mt-2 flex gap-2">
                <Badge type={detail.rule?.rule_type} />
                <span className="text-xs text-muted" style={{ lineHeight: '1.8' }}>
                  from {detail.rule?.source_document?.split('/').pop()}
                </span>
              </div>
            </div>

            {detail.fol && (
              <div className="detail-section">
                <h4>First-Order Logic (FOL)</h4>
                <div className="code-block">
                  {detail.fol.deontic_formula || detail.fol.formula || '—'}
                </div>
                {detail.fol.deontic_type && (
                  <div className="mt-2 text-xs text-muted">
                    Deontic type: <strong>{detail.fol.deontic_type}</strong>
                  </div>
                )}
              </div>
            )}

            <div className="detail-section">
              <h4>SHACL Shape (Turtle)</h4>
              <div className="code-block" style={{ maxHeight: '300px', overflow: 'auto' }}>
                {detail.shacl_shape || 'No shape generated for this rule'}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

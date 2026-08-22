/* Data tab — stat tiles, hub coverage banner, version lists, relationships. */

import { useState } from 'react'
import { StatCard, StatusBadge, DataListItem, PanelContainer } from './shared'
import { clearGraph } from '../../api'

export default function DataTab({ versions, managedVersions, relationships, hubSummary, onDataChange }) {
  const [clearing, setClearing] = useState(false)

  const handleClear = async () => {
    if (!window.confirm('Clear the entire compatibility graph? This cannot be undone.')) return
    setClearing(true)
    try {
      const result = await clearGraph()
      if (result.error || result.status === 'FAIL') alert(result.error || 'Failed to clear graph.')
      else onDataChange()
    } catch (e) { alert(e.message) }
    setClearing(false)
  }

  return (
    <PanelContainer>
      {/* Stat tiles */}
      <div className="stats-grid">
        <StatCard value={versions.length} label="Total versions" />
        <StatCard value={managedVersions.length} label="Managed versions" />
        <StatCard value={relationships.length} label="Relationships" />
        <StatCard value={hubSummary.downloaded_count ?? 0} label="Hub records" />
      </div>

      {/* Hub coverage banner */}
      {hubSummary.total && hubSummary.total > 0 && (
        <div style={{ background: '#243a1f', border: '1px solid #35611d', borderRadius: 8, padding: 14, marginBottom: 16 }}>
          <span style={{ color: '#86efac' }}>🏢 Hub Coverage: {hubSummary.downloaded_count ?? 0} / {hubSummary.total}</span>
        </div>
      )}

      {/* Versions list */}
      <h3 style={{ color: '#9ddfff', margin: '20px 0 10px' }}>Supported Versions</h3>
      <div className="data-list">
        {versions.map(v => (
          <DataListItem key={v.version} label={v.version}
            right={<StatusBadge status={v.status} />} />
        ))}
      </div>

      {/* Managed versions */}
      <h3 style={{ color: '#9ddfff', margin: '20px 0 10px' }}>Managed Versions</h3>
      <div className="data-list">
        {managedVersions.map(v => (
          <DataListItem key={v.version} label={v.version}
            right={<StatusBadge status={v.status} />} />
        ))}
      </div>

      {/* Relationships */}
      <h3 style={{ color: '#9ddfff', margin: '20px 0 10px' }}>Upgrade Relationships</h3>
      <div className="data-list" style={{ maxHeight: 300 }}>
        {relationships.slice(0, 50).map((r, i) => (
          <DataListItem key={i} label={`${r.source} → ${r.target}`}
            right={<StatusBadge status={r.status || 'UNKNOWN'} />} />
        ))}
      </div>

      {/* Clear graph */}
      <button onClick={handleClear} disabled={clearing}
              style={{ marginTop: 20, background: '#991b1b', color: '#fff' }}>
        {clearing ? 'Clearing...' : '🗑️ Clear Graph'}
      </button>
    </PanelContainer>
  )
}

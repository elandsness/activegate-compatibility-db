/* Ingest tab — import all data and single-source ingestion. */

import { useState } from 'react'
import { ingest, downloadBlobFile } from '../api'

export default function IngestTab({ onDataChange }) {
  const [error, setError]      = useState('')
  const [loading, setLoading]  = useState(false)
  const [progress, setProgress]= useState(null)

  const handleIngestAll = async () => {
    setError(''); setProgress({ step: 'Ingesting all sources...', pct: 0 })
    try {
      setLoading(true)
      const result = await ingest('all')
      if (result.error) setError(result.error)
      setProgress({ step: result.status === 'success' ? 'Complete' : 'Failed', pct: 100 })
      if (result.status === 'success') onDataChange()
    } catch (e) { setError(e.message); setProgress(null) }
    setLoading(false)
  }

  const handleSingle = async (source, extraUrl) => {
    setError(''); setProgress({ step: `Ingesting ${source}`, pct: 0 })
    try {
      setLoading(true)
      const result = await ingest(source, extraUrl)
      if (result.error) setError(result.error)
      else setProgress({ step: `${source} done`, pct: 100 })
    } catch (e) { setError(e.message); setProgress(null) }
    setLoading(false)
  }

  return (
    <div className="data-container">
      <h2 style={{ marginTop: 0, color: '#00d4ff' }}>Ingest Data</h2>
      <p style={{ marginBottom: 16, color: '#888' }}>Import compatibility data from one or multiple sources.</p>

      {/* Import All */}
      <div className="ingest-form" style={{ marginBottom: 24 }}>
        <label style={{ color: '#ccc', fontWeight: 'bold' }}>Import all data (releases, managed, relationships, hub)</label>
        <p style={{ color: '#888', fontSize: '0.9rem', marginBottom: 10 }}>Scrapes and ingests all available data sources.</p>
        <button onClick={handleIngestAll} disabled={loading}>
          {loading ? 'Importing...' : 'Import All Data'}
        </button>
        {progress && <ProgressBar active={progress.step !== 'Complete'} label={progress.step} />}
      </div>

      {/* Advanced single-source ingestion */}
      <div className="ingest-form">
        <h3 style={{ color: '#9ddfff', marginBottom: 12 }}>Advanced — Ingest a specific source</h3>
        <label style={{ color: '#ccc' }}>Source type:</label>
        <select id="sourceType" style={{ width: '100%', marginTop: 6, marginBottom: 8, background: '#1a1a2e', color: '#eee', border: 'none', borderRadius: 8, padding: 10 }} defaultValue="releases">
          <option value="releases">Releases (versions & support status)</option>
          <option value="managed-versions">Managed Versions</option>
          <option value="relationships">Relationships (upgrade paths)</option>
          <option value="hub">Dynatrace Hub Data</option>
          <option value="eos">End-of-Support Data</option>
          <option value="url">Custom URL Source</option>
        </select>

        <div id="extraUrlRow" style={{ display: 'none', marginTop: 10 }}>
          <label style={{ color: '#ccc' }}>URL:</label>
          <textarea id="ingest-url" placeholder="https://example.com/data.json" rows={3} style={{ width: '100%', background: '#1a1a2e', color: '#eee', border: 'none', borderRadius: 8, padding: 10, marginTop: 6, resize: 'vertical' }} />
        </div>

        <button id="btnIngest" onClick={() => {
          const src = document.getElementById('sourceType').value
          const extraUrl = document.getElementById('ingest-url')?.value
          handleSingle(src, extraUrl || undefined)
        }} style={{ marginTop: 10 }}>Ingest Source</button>
      </div>

      {/* Results area */}
      {error && <div className="notification notification-error" style={{ marginTop: 16, background: '#7f1d1d', border: '1px solid #b91c1c', color: '#fecaca', padding: 12, borderRadius: 8 }}>{error}</div>}
    </div>
  )
}

/* Tiny inline progress bar (avoids importing shared for just this) */
function ProgressBar({ active, label }) {
  if (!active) return <p style={{ color: '#86efac', marginTop: 10 }}>✅ {label}</p>
  return (<>
    <div style={{ color: '#9ddfff', fontSize: '0.88rem' }}>{label ?? 'Import in progress.'}</div>
    <div className="progress-track" role="progressbar" aria-label="Import progress">
      <div className="progress-bar" />
    </div>
  </>)
}

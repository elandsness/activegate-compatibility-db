/* Batch tab — upload a CSV, get results back as a downloadable file. */

import { useState } from 'react'
import { downloadTemplate, uploadBatch } from '../api'

export default function BatchCheckTab() {
  const [file, setFile]     = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]    = useState('')
  const [resultMsg, setResultMsg] = useState('')

  const handleDownloadTemplate = async () => {
    try {
      const blob = await downloadTemplate()
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'batch-check-template.csv'
      document.body.appendChild(a); a.click(); a.remove()
    } catch (e) { setError(e.message) }
  }

  const handleUpload = async () => {
    if (!file || loading) return
    setLoading(true); setError(''); setResultMsg('')
    try {
      const blob = await uploadBatch(file)
      // Trigger download of results — backend returns CSV with compatibility results
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'batch-results.csv'
      document.body.appendChild(a); a.click(); a.remove()
      setResultMsg('✅ Results downloaded.')
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  return (
    <div className="data-container">
      <h2 style={{ marginTop: 0, color: '#00d4ff' }}>Batch CSV Check</h2>
      <p style={{ marginBottom: 16, color: '#888' }}>Upload a CSV of version pairs for batch compatibility checking.</p>

      {/* Download template */}
      <button onClick={handleDownloadTemplate} disabled={loading} style={{ marginBottom: 20 }}>⬇️ Download Template</button>

      {/* File input */}
      <div className="ingest-form" style={{ marginTop: 16 }}>
        <label style={{ color: '#ccc', fontWeight: 'bold' }}>Upload CSV file</label>
        <input type="file" accept=".csv" onChange={e => setFile(e.target.files[0])}
               style={{ marginTop: 10, marginBottom: 10 }} />
        {file && <p style={{ color: '#9ddfff', marginTop: 6 }}>Selected: {file.name}</p>}
        <button onClick={handleUpload} disabled={!file || loading}>Process CSV</button>
        {loading && (<>
          <div style={{ color: '#9ddfff', fontSize: '0.88rem', marginTop: 14 }}>Processing...</div>
          <div className="progress-track" role="progressbar"><div className="progress-bar" /></div>
        </>)}
      </div>

      {resultMsg && <p style={{ color: '#86efac', marginTop: 12 }}>{resultMsg}</p>}
      {error   && <p style={{ color: '#fca5a5', marginTop: 12 }}>{error}</p>}
    </div>
  )
}

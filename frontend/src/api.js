/* Shared API helpers for the frontend */

const API = '/api'

export async function parseApiResponse (response) {
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return await response.json()
  const text = await response.text()
  return { error: `Unexpected ${response.status} response: ${text.slice(0, 200)}` }
}

export async function fetchData () {
  try {
    const [vRes, mvRes, rRes, hRes] = await Promise.all([
      fetch(`${API}/data/versions`),
      fetch(`${API}/data/managed-versions`),
      fetch(`${API}/data/relationships`),
      fetch(`${API}/data/hub-summary`)
    ])
    const vData     = await parseApiResponse(vRes)
    const mvData    = await parseApiResponse(mvRes)
    const rData     = await parseApiResponse(rRes)
    const hData     = await parseApiResponse(hRes)
    return { versions: vData.versions || [], managedVersions: mvData.versions || [], relationships: rData.relationships || [], hubSummary: hData || {} }
  } catch (e) { console.error('Failed to fetch data:', e); return { versions: [], managedVersions: [], relationships: [], hubSummary: {} } }
}

export async function checkCompatibility (payload) {
  const res = await fetch(`${API}/check`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  return parseApiResponse(res)
}

export async function chat (message, context = {}) {
  const res = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, context }) })
  return parseApiResponse(res)
}

export async function ingest (source, extraUrl) {
  const payload = { source }
  if (source === 'url' && extraUrl) payload.url = extraUrl
  const res = await fetch(`${API}/ingest`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  return parseApiResponse(res)
}

export async function clearGraph () {
  const res = await fetch(`${API}/admin/clear-graph`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
  return parseApiResponse(res)
}

export async function fetchGraph (activegateVersion) {
  const params = new URLSearchParams({ limit: '700' })
  if (activegateVersion) params.set('activegate_version', activegateVersion)
  const res = await fetch(`${API}/data/graph?${params}`)
  return parseApiResponse(res)
}

export async function downloadTemplate () {
  const res = await fetch(`${API}/check/template`)
  if (!res.ok) { const data = await parseApiResponse(res); throw new Error(data.error || `Template download failed with ${res.status}`) }
  return res.blob()
}

export async function uploadBatch (file) {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API}/check/batch-csv`, { method: 'POST', body: formData })
  if (!res.ok) { const data = await parseApiResponse(res); throw new Error(data.error || `Batch processing failed with ${res.status}`) }
  return res.blob()
}

function downloadBlob (blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

export function downloadBlobFile (blob, filename) { downloadBlob(blob, filename) }

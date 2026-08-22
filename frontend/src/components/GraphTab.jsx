/* Graph tab — interactive vis.Network diagram with toolbar and detail panel. */

import { useState, useEffect, useRef } from 'react'
import { fetchGraph } from '../../api'

export default function GraphTab({ versions }) {
  const containerRef = useRef(null)
  const networkRef   = useRef(null)
  const [data, setData]   = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading]   = useState(false)

  // Active version filter (all versions that have status, not UNKNOWN/END_OF_SUPPORT)
  const [activeVersion, setActiveVersion] = useState(() => {
    if (versions.length === 0) return ''
    const latest = versions.filter(v => v.status !== 'UNKNOWN' && v.status !== 'END_OF_SUPPORT').pop()
    return latest ? latest.version : ''
  })

  // Text filter
  const [filterText, setFilterText] = useState('')

  useEffect(() => { load() }, [])

  const load = async () => {
    setLoading(true)
    try {
      const res = await fetchGraph(activeVersion || undefined)
      if (res.nodes && res.edges) setData(res)
    } catch (e) { console.error('Failed to load graph:', e) }
    setLoading(false)
  }

  // vis-network init
  useEffect(() => {
    if (!data || !containerRef.current) return
    const script = document.createElement('script')
    script.src = 'https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js'
    script.onload = () => {
      try {
        // vis is global after load
        const { Network, DataStore, DataView } = window.vis ?? {}
        if (!Network) return
        const nodes = new DataStore(data.nodes.map(n => ({ ...n, id: String(n.id), label: n.label, title: n.title })))
        const edges = new DataStore(data.edges.map(e => ({ ...e, id: String(e.id) })))
        const net = new Network(containerRef.current, { nodes, edges }, {
          interaction: { zoomView: true, dragView: true, dragNodes: true },
          physics: { enabled: true, barnesHut: { centralGravity: 0.1, springLength: 100 } },
          layout: { improvedLayout: true },
        })
        net.on('click', params => {
          const nodeId = params.nodes[0]
          if (nodeId) setSelected(data.nodes.find(n => String(n.id) === String(nodeId)))
        })
        networkRef.current = net
      } catch (e) { console.error('vis-network error:', e) }
    }
    document.head.appendChild(script)
    return () => { networkRef.current?.destroy(); script.remove() }
  }, [data])

  // Filter nodes by text
  const handleFilter = () => {
    if (!networkRef.current || !filterText.trim()) { load(); return }
    const q = filterText.toLowerCase()
    const filtered = data.nodes.filter(n => n.label.toLowerCase().includes(q) || (n.title || '').toLowerCase().includes(q))
    const ids = new Set(filtered.map(n => String(n.id)))
    networkRef.current.setData({
      nodes: data.nodes.filter(n => ids.has(String(n.id))),
      edges: data.edges,
    })
  }

  return (
    <div>
      <h2 style={{ marginTop: 0, color: '#00d4ff' }}>Compatibility Graph</h2>

      {/* Toolbar */}
      <div className="graph-toolbar" style={{ marginBottom: 16 }}>
        <select value={activeVersion} onChange={e => { setActiveVersion(e.target.value); setSelected(null) }}>
          <option value="">All ActiveGate versions</option>
          {versions.filter(v => v.status !== 'UNKNOWN' && v.status !== 'END_OF_SUPPORT').map(v => (
            <option key={v.version} value={v.version}>{v.version}</option>
          ))}
        </select>
        <input type="text" placeholder="Filter by label or title…" value={filterText} onChange={e => setFilterText(e.target.value)} />
        <button onClick={handleFilter}>Filter</button>
        <button onClick={() => { load(); setSelected(null); setFilterText('') }}>Reset</button>
      </div>

      {/* Legend */}
      <div className="graph-legend">
        <div className="legend-item"><span className="legend-swatch" style={{ background: '#00d4ff' }} /> ActiveGate &rarr; version</div>
        <div className="legend-item"><span className="legend-swatch" style={{ background: '#22c55e' }} /> Compatible</div>
        <div className="legend-item"><span className="legend-swatch" style={{ background: '#f59e0b' }} /> Questionable</div>
        <div className="legend-item"><span className="legend-swatch" style={{ background: '#ef4444' }} /> Incompatible</div>
        <div className="legend-item"><span className="legend-swatch" style={{ background: '#94a3b8' }} /> Unknown</div>
      </div>

      {/* Graph layout */}
      <div className="graph-layout">
        <div className="graph-canvas" ref={containerRef} style={{ overflow: 'hidden' }}>
          {loading && <div className="loading">Loading graph…</div>}
        </div>
        <div className="graph-sidepanel">
          <h4>Node Details</h4>
          {selected ? (<>
            <p><strong>{selected.label}</strong></p>
            <div className="panel-section">
              {(selected.title || selected.group) && <div className="panel-kv"><span>Title</span><span>{selected.title}</span></div>}
              {selected.category && <div className="panel-kv"><span>Category</span><span>{selected.category}</span></div>}
              {selected.status && <div className="panel-kv"><span>Status</span><span>{selected.status}</span></div>}
              {selected.releaseDate && <div className="panel-kv"><span>Release</span><span>{selected.releaseDate}</span></div>}
            </div>
            <div className="panel-section">
              <strong>Compatibility:</strong>
              <div className="panel-list">
                {selected.compatible?.map((c, i) => (
                  <div key={i}><DataListItem label={c} right={<StatusBadge status="GO" />} /></div>
                )) || <span style={{ color: '#888' }}>No data</span>}
              </div>
            </div>
          </>)
          : null}
          {!selected && !data && <p style={{ color: '#888' }}>No graph loaded yet.</p>}
          {!selected && data && <p style={{ color: '#888' }}>Click a node to see details.</p>}
        </div>
      </div>
    </div>
  )
}

/* Inline helpers so this component is self-contained. */
import { StatCard, StatusBadge, DataListItem } from './shared'

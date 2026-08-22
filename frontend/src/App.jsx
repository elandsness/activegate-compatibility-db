/** Main app shell with tab navigation and shared data fetching. */

import { useState, useEffect } from 'react'
import { fetchData as loadAllData } from './api'
import { IngestTab }     from './components/IngestTab'
import { ChatTab }       from './components/ChatTab'
import { BatchCheckTab } from './components/BatchCheckTab'
import { DataTab }       from './components/DataTab'
import { GraphTab }      from './components/GraphTab'

const TABS = [
  ['ingest', '📥 Ingest Data'],
  ['chat',   '💬 Chat'],
  ['batch',  '📄 Batch CSV Check'],
  ['data',   '📊 Data'],
  ['graph',  '🕸️ Graph'],
]

export default function App() {
  const [activeTab, setActiveTab]     = useState('ingest')
  const [versions, setVersions]        = useState([])
  const [managedVersions, setManagedVersions] = useState([])
  const [relationships, setRelationships]   = useState([])
  const [hubSummary, setHubSummary]         = useState({})

  useEffect(() => { load() }, [])

  const load = async () => {
    try {
      const data = await loadAllData()
      setVersions(data.versions || [])
      setManagedVersions(data.managedVersions || [])
      setRelationships(data.relationships || [])
      setHubSummary(data.hubSummary || {})
    } catch (e) { console.error('Failed to fetch data:', e) }
  }

  return (
    <div className="app">
      <div className="header">
        <h1>🔧 ActiveGate Compatibility Intelligence</h1>
        <p>Check upgrade compatibility between Dynatrace ActiveGate versions</p>
      </div>

      <div className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key}
                  className={`tab ${activeTab === key ? 'active' : ''}`}
                  onClick={() => setActiveTab(key)}
          >{label}</button>
        ))}
      </div>

      {activeTab === 'ingest' && <IngestTab onDataChange={load} />}
      {activeTab === 'chat'   && <ChatTab />}
      {activeTab === 'batch'  && <BatchCheckTab />}
      {activeTab === 'data'
        ? <DataTab versions={versions} managedVersions={managedVersions}
                   relationships={relationships} hubSummary={hubSummary} onDataChange={load} />
        : null}
      {activeTab === 'graph' && <GraphTab versions={versions} />}
    </div>
  )
}

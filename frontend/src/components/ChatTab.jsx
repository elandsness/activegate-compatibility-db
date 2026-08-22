/* Chat tab — natural-language compatibility assistant. */

import { useState, useRef } from 'react'
import { chat } from '../../api'

export default function ChatTab() {
  const [messages, setMessages]   = useState([])
  const [input, setInput]           = useState('')
  const [sending, setSending]       = useState(false)
  const [error, setError]           = useState('')
  const bottomRef = useRef(null)

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setSending(true)
    const ctx = messages.length > 0 ? messages.slice(-4).map(m => ({ role: m.role, content: m.content })) : {}
    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setError('')
    try {
      const res = await chat(text, ctx)
      if (res.error || !res.answer) { setError(res.error || 'No answer returned'); return }
      setMessages(prev => [...prev, { role: 'assistant', content: res.answer }])
    } catch (e) { setError(e.message) }
    setSending(false)
  }

  return (
    <div className="chat-container">
      <h2 style={{ marginBottom: 16, color: '#00d4ff' }}>Compatibility Assistant</h2>
      <div className="messages" ref={bottomRef}>
        {messages.length === 0 && (
          <p style={{ textAlign: 'center', color: '#888', marginTop: 100 }}>Ask anything about Dynatrace ActiveGate compatibility.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            {m.content}
            {m.versionInfo && <div className="version-info">Version context: {m.versionInfo}</div>}
          </div>
        ))}
      </div>
      <div className="input-container">
        <input type="text" value={input} onChange={e => setInput(e.target.value)}
               onKeyDown={e => e.key === 'Enter' && send()} disabled={sending}
               placeholder="Ask about version compatibility..." />
        <button onClick={send} disabled={sending || !input.trim()}>Send</button>
      </div>
      {error && <p style={{ color: '#fca5a5', marginTop: 10, textAlign: 'center' }}>{error}</p>}
    </div>
  )
}

/* Shared presentation components */

export function StatCard({ value, label }) {
  return (
    <div className="stat-card">
      <h3>{value}</h3>
      <p>{label}</p>
    </div>
  )
}

export function StatusBadge({ status }) {
  const cls = status === 'GO'           ? 'go'
            : status === 'NO_GO'         ? 'no-go'
            : status === 'GO_WITH_CAUTION' ? 'caution'
            : ''
  return <span className={`status-badge ${cls}`}>{status}</span>
}

export function DataListItem({ label, right }) {
  return (
    <div className="data-item">
      <span>{label}</span>
      {right ?? null}
    </div>
  )
}

export function ProgressBar({ active }) {
  if (!active) return null
  return (
    <>
      <div style={{ color: '#9ddfff', fontSize: '0.88rem' }}>
        Import in progress. This can take around 45-60 seconds.
      </div>
      <div className="progress-track" role="progressbar" aria-label="Import progress">
        <div className="progress-bar" />
      </div>
    </>
  )
}

export function PanelContainer({ children }) {
  return <div className="data-container">{children}</div>
}

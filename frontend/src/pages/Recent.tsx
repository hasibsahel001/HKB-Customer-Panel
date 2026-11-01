import { useState } from 'react'
import { formatTime } from '../format'
import type { RecentItem } from '../types'
import { Dot, Modal } from '../ui'

function label(item: RecentItem): string {
  return item.username ?? item.identity ?? item.ip
}

export function RecentModal({
  items,
  canClearAll,
  onPick,
  onClear,
  onClose,
}: {
  items: RecentItem[]
  canClearAll: boolean
  onPick: (item: RecentItem) => void
  onClear: (scope: 'mine' | 'all') => Promise<void>
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [confirm, setConfirm] = useState<'mine' | 'all' | null>(null)
  const [busy, setBusy] = useState(false)
  const q = query.trim().toLowerCase()
  const shown = items.filter(
    (item) =>
      !q ||
      [item.username, item.identity, item.ip, item.tid].some((value) => (value ?? '').toLowerCase().includes(q)),
  )

  async function clear(scope: 'mine' | 'all') {
    if (confirm !== scope) {
      setConfirm(scope)
      return
    }
    setBusy(true)
    try {
      await onClear(scope)
    } finally {
      setBusy(false)
      setConfirm(null)
    }
  }

  return (
    <Modal title={`Customers you opened in the last 24 hours (${items.length})`} onClose={onClose}>
      <input
        style={{ width: '100%', marginTop: 10 }}
        placeholder="Search by PPPoE username, IP or Technical ID"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search recent customers"
      />
      <div className="recent-list">
        {shown.map((item) => (
          <button
            key={`${item.ip}-${item.tid}`}
            className="recent-item"
            onClick={() => {
              onPick(item)
              onClose()
            }}
          >
            <Dot level={item.overall} />
            <span>
              <strong>{label(item)}</strong>
              <span className="muted small mono">
                {item.ip} · TID {item.tid} · {formatTime(item.checked_at)}
              </span>
            </span>
          </button>
        ))}
        {shown.length === 0 && <p className="muted">No matching customers.</p>}
      </div>
      <div className="toolbar" style={{ marginTop: 16 }}>
        <button className="btn secondary danger" disabled={busy} onClick={() => void clear('mine')}>
          {confirm === 'mine' ? 'Click again to clear my recents' : 'Clear my recents'}
        </button>
        {canClearAll && (
          <button className="btn secondary danger" disabled={busy} onClick={() => void clear('all')}>
            {confirm === 'all' ? "Click again to clear everyone's" : "Clear everyone's recents"}
          </button>
        )}
      </div>
    </Modal>
  )
}
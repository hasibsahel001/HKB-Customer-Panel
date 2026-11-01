import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, toApiError } from '../api'
import { useAuth } from '../auth'
import { formatTime } from '../format'
import type { AuditItem } from '../types'
import { ErrorBox } from '../ui'

const ACTIONS = [
  'setup.super_admin_created',
  'auth.login',
  'auth.login_failed',
  'auth.login_blocked',
  'auth.logout',
  'auth.password_changed',
  'auth.password_change_failed',
  'auth.session_revoked',
  'auth.permission_denied',
  'customer.check',
  'router.queue_saved',
  'router.queue_deleted',
  'router.queues_deleted_all',
  'router.reboot',
  'users.created',
  'users.updated',
  'users.deleted',
  'users.password_reset',
  'audit.cleared',
  'recent.cleared_mine',
  'recent.cleared_all',
]

const PAGE_SIZE = 50

export function AuditPage() {
  const { can } = useAuth()
  const [items, setItems] = useState<AuditItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [older, setOlder] = useState('')
  const [armed, setArmed] = useState(false)
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setError(null)
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) })
    if (action) params.set('action', action)
    try {
      const data = await api<{ total: number; items: AuditItem[] }>(`/api/audit?${params}`)
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      setError(toApiError(e))
    }
  }, [offset, action])

  useEffect(() => {
    void load()
  }, [load])

  async function clear() {
    if (!armed) {
      setArmed(true)
      return
    }
    setArmed(false)
    setError(null)
    try {
      const query = older ? `?older_than_days=${older}` : ''
      const result = await api<{ deleted: number }>(`/api/audit${query}`, { method: 'DELETE' })
      setMessage(`Deleted ${result.deleted} entries.`)
      setOffset(0)
      await load()
    } catch (e) {
      setError(toApiError(e))
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <h2>Audit log ({total})</h2>
        <div className="toolbar">
          <select
            value={action}
            onChange={(e) => {
              setOffset(0)
              setAction(e.target.value)
            }}
            aria-label="Filter by action"
          >
            <option value="">All actions</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <button className="btn secondary" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>
      {can('audit.delete') && (
        <div className="toolbar" style={{ margin: '8px 0' }}>
          <select
            value={older}
            onChange={(e) => {
              setOlder(e.target.value)
              setArmed(false)
            }}
            aria-label="Delete entries older than"
          >
            <option value="">Delete everything</option>
            <option value="7">Older than 7 days</option>
            <option value="30">Older than 30 days</option>
            <option value="90">Older than 90 days</option>
          </select>
          <button className="btn secondary danger" onClick={() => void clear()}>
            {armed ? 'Click again to delete' : 'Delete entries'}
          </button>
          <span className="muted small">The deletion itself is recorded as audit.cleared.</span>
        </div>
      )}
      {message && <div className="ok-box">{message}</div>}
      <ErrorBox error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>User</th>
              <th>Action</th>
              <th>Target</th>
              <th>IP</th>
              <th>Result</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{formatTime(item.created_at)}</td>
                <td>{item.username ?? '-'}</td>
                <td className="mono">{item.action}</td>
                <td className="mono">{item.target ?? '-'}</td>
                <td className="mono">{item.ip ?? '-'}</td>
                <td>
                  <span className={`badge ${item.success ? 'badge-normal' : 'badge-critical'}`}>
                    {item.success ? 'OK' : 'Failed'}
                  </span>
                </td>
                <td className="debug">{item.details ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar" style={{ marginTop: 10 }}>
        <button
          className="btn secondary"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </button>
        <button
          className="btn secondary"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </button>
      </div>
    </section>
  )
}
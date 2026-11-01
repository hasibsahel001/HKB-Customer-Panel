import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, ApiError, toApiError } from '../api'
import { useAuth } from '../auth'
import { formatTime } from '../format'
import type { Me, SessionItem } from '../types'
import { ErrorBox } from '../ui'

export function AccountPage() {
  const { me, updateMe } = useAuth()
  const [sessions, setSessions] = useState<SessionItem[]>([])
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [message, setMessage] = useState('')

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await api<SessionItem[]>('/api/auth/sessions'))
    } catch (e) {
      setError(toApiError(e))
    }
  }, [])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  async function changeTheme(theme: string) {
    setError(null)
    try {
      updateMe(await api<Me>('/api/auth/me', { method: 'PATCH', body: { theme } }))
    } catch (e) {
      setError(toApiError(e))
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setMessage('')
    try {
      await api('/api/auth/change-password', {
        method: 'POST',
        body: { current_password: current, new_password: next },
      })
      setCurrent('')
      setNext('')
      setMessage('Password changed. Your other sessions were signed out.')
      await loadSessions()
    } catch (e) {
      setError(toApiError(e))
    }
  }

  async function revoke(id: number) {
    setError(null)
    try {
      await api(`/api/auth/sessions/${id}`, { method: 'DELETE' })
      await loadSessions()
    } catch (e) {
      setError(toApiError(e))
    }
  }

  if (!me) return null

  return (
    <>
      <ErrorBox error={error} />
      <div className="grid">
        <section className="card">
          <h2>Profile</h2>
          <p>
            Signed in as <strong>{me.username}</strong> ({me.role})
          </p>
          <label className="field">
            Theme
            <select value={me.theme} onChange={(e) => void changeTheme(e.target.value)}>
              <option value="system">Follow system</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
        </section>
        <section className="card">
          <h2>Change password</h2>
          <form className="stack" onSubmit={changePassword}>
            <label className="field">
              Current password
              <input
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                autoComplete="current-password"
              />
            </label>
            <label className="field">
              New password (at least 10 characters)
              <input
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            {message && <div className="ok-box">{message}</div>}
            <button className="btn" type="submit" disabled={!current || !next}>
              Change password
            </button>
          </form>
        </section>
        <section className="card wide">
          <h2>Sessions</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Last seen</th>
                  <th>IP</th>
                  <th>Browser</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.id}>
                    <td>{formatTime(s.created_at)}</td>
                    <td>{formatTime(s.last_seen_at)}</td>
                    <td className="mono">{s.ip ?? '-'}</td>
                    <td className="debug">{s.user_agent ?? '-'}</td>
                    <td>
                      {s.current ? (
                        <span className="badge badge-normal">This session</span>
                      ) : (
                        <button className="btn secondary" onClick={() => void revoke(s.id)}>
                          Sign out
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  )
}
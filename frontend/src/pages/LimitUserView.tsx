import { useEffect, useState } from 'react'
import { ApiError, api, toApiError } from '../api'
import type { ActionCustomer } from '../actionTypes'
import { ErrorBox, Spinner } from '../ui'

interface LimitResult {
  allow: 'added' | 'updated'
  block: 'added' | 'updated'
  scheduled_on_router: boolean
  seconds: number
}

// When each router's limit ends, so reopening this page still shows the countdown.
const ACTIVE = new Map<string, number>()

export function LimitUserView({ customer }: { customer: ActionCustomer }) {
  const key = `${customer.ip}/${customer.tid}`
  const [busy, setBusy] = useState<'start' | 'stop' | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [note, setNote] = useState('')
  const [endsAt, setEndsAt] = useState<number | null>(() => {
    const saved = ACTIVE.get(key)
    return saved && saved > Date.now() ? saved : null
  })
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    if (endsAt === null) return
    const timer = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(timer)
  }, [endsAt])

  const remaining = endsAt === null ? 0 : Math.max(0, Math.ceil((endsAt - now) / 1000))
  const active = endsAt !== null && remaining > 0

  async function start() {
    setBusy('start')
    setError(null)
    setNote('')
    try {
      const result = await api<LimitResult>('/api/router/manage/limit-user', {
        method: 'POST',
        body: { ip: customer.ip, tid: customer.tid },
      })
      const end = Date.now() + result.seconds * 1000
      ACTIVE.set(key, end)
      setEndsAt(end)
      setNow(Date.now())
      const reused = result.allow === 'updated' || result.block === 'updated'
      setNote(
        `${reused ? 'The existing queues were switched on and updated.' : 'The queues were created.'} They are removed ` +
          `automatically after ${Math.round(result.seconds / 60)} minutes` +
          `${result.scheduled_on_router ? ' (the router also has a backup timer).' : '.'}`,
      )
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(null)
    }
  }

  async function stop() {
    setBusy('stop')
    setError(null)
    try {
      await api('/api/router/manage/limit-user/clear', { method: 'POST', body: { ip: customer.ip, tid: customer.tid } })
      ACTIVE.delete(key)
      setEndsAt(null)
      setNote('The limit queues were removed.')
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <p className="muted small">
        Pushes the customer's devices down so you can reach the router: the access point addresses keep 10M, and
        everything else on 10.10.10.0/24 is cut to 300k. The two queues (<code>allow-h</code> and{' '}
        <code>block-h</code>) are put first on the router and are removed automatically after 2 minutes. They are
        only added when you press the button.
      </p>
      <ErrorBox error={error} />
      <div className="toolbar">
        <button className="btn" disabled={busy !== null} onClick={() => void start()}>
          {busy === 'start' ? (
            <>
              <Spinner /> Limiting…
            </>
          ) : active ? (
            'Limit again (restart 2 minutes)'
          ) : (
            'Limit user for 2 minutes'
          )}
        </button>
        {active && (
          <button className="btn secondary" disabled={busy !== null} onClick={() => void stop()}>
            {busy === 'stop' ? 'Removing…' : 'Release now'}
          </button>
        )}
      </div>
      {active && (
        <div className="limit-timer" role="status">
          <span className="limit-dot" /> Limit is on · removed in{' '}
          <strong className="mono">
            {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}
          </strong>
        </div>
      )}
      {note && <div className="ok-box">{note}</div>}
    </>
  )
}
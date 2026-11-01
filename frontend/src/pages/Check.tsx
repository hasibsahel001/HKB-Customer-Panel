import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError, toApiError } from '../api'
import { useAuth } from '../auth'
import { mergeDiagnostics } from '../diagnosis'
import { ageSeconds, formatAge, formatTime } from '../format'
import type { LiveResult, RecentItem, Report } from '../types'
import { ErrorBox, Spinner } from '../ui'
import { useLiveDevices } from '../useLiveDevices'
import { ManageSidebar } from './ManageSidebar'
import { CustomerHero, Dashboard, DashboardSkeleton } from './Dashboard'
import { RecentModal } from './Recent'
import { dataOf } from './shared'
import type { LiveState } from './shared'

interface Query {
  ip: string
  tid: string
}

const IDLE_LIVE: LiveState = { data: null, loading: false, failed: false }

export function CheckPage({ active = true }: { active?: boolean }) {
  const { can } = useAuth()
  const [ip, setIp] = useState('')
  const [tid, setTid] = useState('')
  const [report, setReport] = useState<Report | null>(null)
  const [live, setLive] = useState<LiveState>(IDLE_LIVE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [now, setNow] = useState(Date.now())
  const [recent, setRecent] = useState<RecentItem[]>([])
  const [showRecent, setShowRecent] = useState(false)
  const lastQuery = useRef<Query | null>(null)
  const busy = useRef(false)

  const loadRecent = useCallback(async () => {
    try {
      const data = await api<{ items: RecentItem[] }>('/api/customer/recent')
      setRecent(data.items)
    } catch {
      // The recent list is a convenience; failing to load it is not an error for the user.
    }
  }, [])

  const run = useCallback(async (query: Query) => {
    if (busy.current) return
    busy.current = true
    setLoading(true)
    setError(null)
    setLive(IDLE_LIVE)
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 70_000)
    try {
      const result = await api<Report>('/api/customer/check', {
        method: 'POST',
        body: query,
        signal: controller.signal,
      })
      lastQuery.current = query
      setReport(result)
      setLoading(false)

      setLive({ data: null, loading: true, failed: false })
      try {
        const measured = await api<LiveResult>('/api/customer/live', {
          method: 'POST',
          body: query,
          signal: controller.signal,
        })
        setLive({ data: measured, loading: false, failed: false })
      } catch {
        setLive({ data: null, loading: false, failed: true })
      }
    } catch (e) {
      setError(toApiError(e))
    } finally {
      clearTimeout(timer)
      busy.current = false
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  const liveDevices = useLiveDevices(report?.ip ?? null, report?.technical_id ?? null, active && !!report && !loading)

  const diagnostics = useMemo(
    () => (report ? mergeDiagnostics(report.diagnostics, live.data?.diagnostics.findings ?? []) : null),
    [report, live.data],
  )

  function start(query: Query) {
    if (!query.ip || !query.tid) return
    setIp(query.ip)
    setTid(query.tid)
    const previous = lastQuery.current
    if (!previous || previous.ip !== query.ip || previous.tid !== query.tid) {
      setReport(null)
    }
    void run(query)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    start({ ip: ip.trim(), tid: tid.trim() })
  }

  function clear() {
    if (busy.current) return
    setReport(null)
    setLive(IDLE_LIVE)
    setError(null)
    lastQuery.current = null
  }

  async function openRecent() {
    await loadRecent()
    setShowRecent(true)
  }

  async function clearRecent(scope: 'mine' | 'all') {
    await api(`/api/customer/recent/${scope}`, { method: 'DELETE' })
    await loadRecent()
  }

  if (!can('customer.check')) {
    return <p className="muted">Your role cannot run customer checks.</p>
  }

  const age = report ? ageSeconds(report.fetched_at, now) : 0
  const seconds = report?.timings_ms ? (report.timings_ms.total / 1000).toFixed(1) : null
  const loginSeconds = report?.timings_ms ? (report.timings_ms.connect / 1000).toFixed(1) : null
  const pppoe = report ? dataOf(report.sections.pppoe) : null
  const identity = report ? dataOf(report.sections.identity) : null

  const showSide = !!report && can('router.manage')

  return (
    <div className={`check-shell${showSide ? ' with-side' : ''}`}>
      {showSide && report && (
        <ManageSidebar
          key={`${report.ip}|${report.technical_id}`}
          customer={{
            username: pppoe?.username ?? null,
            identity: identity?.identity ?? null,
            ip: report.ip,
            tid: report.technical_id,
          }}
          report={report}
        />
      )}
      <div className="check-main">
      {(loading || live.loading) && <div className="progress" />}
      <section className="card searchbar">
        <form className="inline" onSubmit={submit}>
          <label className="field">
            PPPoE IP
            <input
              className="big-input"
              value={ip}
              onChange={(e) => setIp(e.target.value)}
              placeholder="100.101.x.x"
              inputMode="decimal"
              autoComplete="off"
              autoFocus
            />
          </label>
          <label className="field">
            Technical ID
            <input
              className="big-input narrow"
              value={tid}
              onChange={(e) => setTid(e.target.value)}
              placeholder="10047"
              inputMode="numeric"
              autoComplete="off"
            />
          </label>
          <button className="btn" type="submit" disabled={loading || !ip.trim() || !tid.trim()}>
            Check
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={loading || live.loading || !lastQuery.current}
            onClick={() => lastQuery.current && void run(lastQuery.current)}
          >
            Refresh
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={loading || live.loading || (!report && !error)}
            onClick={clear}
          >
            Clear
          </button>
          <button className="btn secondary" type="button" onClick={() => void openRecent()}>
            Recent
          </button>
          {loading && (
            <span className="muted">
              <Spinner /> Reading the router…
            </span>
          )}
        </form>
        {report && (
          <div className="checkmeta">
            Updated {formatTime(report.fetched_at)} ({formatAge(age)} ago)
            {seconds && ` · checked in ${seconds} s`}
            {loginSeconds && ` · login ${loginSeconds} s`}
            {report.connect_attempts !== undefined && ` · ${report.connect_attempts} login attempt(s)`}
          </div>
        )}
      </section>
      <ErrorBox error={error} />
      {loading && !report && <DashboardSkeleton />}
      {report && diagnostics && (
        <>
          <CustomerHero report={report} overall={diagnostics.overall} />
          <Dashboard
            report={report}
            live={live}
            liveDevices={liveDevices}
            diagnostics={diagnostics}
            debug={can('debug.view')}
          />
        </>
      )}
      {showRecent && (
        <RecentModal
          items={recent}
          canClearAll={can('users.manage')}
          onPick={(item) => start({ ip: item.ip, tid: item.tid })}
          onClear={clearRecent}
          onClose={() => setShowRecent(false)}
        />
      )}
      </div>
    </div>
  )
}
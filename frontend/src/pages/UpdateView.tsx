import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, toApiError } from '../api'
import type { ActionCustomer, UpdateCheck, UpdateJob, UpdateState } from '../actionTypes'
import { NA, formatTime, show } from '../format'
import { ErrorBox, Spinner } from '../ui'
import { Row } from './shared'

const STATE: Record<UpdateState, { level: string; text: string }> = {
  available: { level: 'warning', text: 'Update available' },
  up_to_date: { level: 'normal', text: 'Already at the latest stable version' },
  major_change: { level: 'serious', text: 'The latest stable version is a different major version; not offered here' },
  error: { level: 'serious', text: 'The router could not check for updates' },
  unknown: { level: 'unknown', text: 'Version information is not available' },
}

export function UpdateView({ customer }: { customer: ActionCustomer }) {
  const [check, setCheck] = useState<UpdateCheck | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const [firmware, setFirmware] = useState(true)
  const [armed, setArmed] = useState<'now' | 'later' | 'fw' | 'fw-reboot' | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<UpdateJob | null>(null)
  const [message, setMessage] = useState('')
  const base = { ip: customer.ip, tid: customer.tid }

  const runCheck = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setCheck(await api<UpdateCheck>('/api/router/update/check', { method: 'POST', body: { ip: customer.ip, tid: customer.tid } }))
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setLoading(false)
    }
  }, [customer.ip, customer.tid])

  useEffect(() => {
    void runCheck()
  }, [runCheck])

  useEffect(() => {
    if (!jobId) return
    let stopped = false
    let timer: number | undefined
    async function poll() {
      try {
        const data = await api<UpdateJob>(`/api/router/update/jobs/${jobId}`)
        if (stopped) return
        setJob(data)
        if (data.state === 'running') timer = window.setTimeout(poll, 3000)
      } catch (e) {
        if (!stopped) setError(toApiError(e))
      }
    }
    void poll()
    return () => {
      stopped = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [jobId])

  async function start(mode: 'now' | 'later') {
    setBusy(true)
    setError(null)
    setArmed(null)
    try {
      const started = await api<{ job_id: string }>('/api/router/update/start', {
        method: 'POST',
        body: { ...base, mode, firmware: firmware && Boolean(check?.firmware.supported) },
      })
      setJob(null)
      setJobId(started.job_id)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  async function upgradeFirmware(reboot: boolean) {
    setBusy(true)
    setError(null)
    setArmed(null)
    setMessage('')
    try {
      await api('/api/router/firmware/upgrade', { method: 'POST', body: { ...base, reboot } })
      setMessage(reboot ? 'The firmware upgrade was sent and the router is rebooting.' : 'The firmware upgrade was sent. It takes effect at the next reboot.')
      void runCheck()
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  const running = job?.state === 'running' || (jobId !== null && job === null)
  const state = check ? STATE[check.state] : null
  const fw = check?.firmware

  return (
    <>
      <p className="muted small">
        The router is updated to the latest stable RouterOS using its own internet connection, so the download loads
        the customer's link. Prefer quiet hours.
      </p>
      <ErrorBox error={error} />
      {loading && (
        <p>
          <Spinner /> Asking the router for the latest stable version…
        </p>
      )}

      {check && state && (
        <>
          <Row k="Installed">{show(check.installed)}</Row>
          <Row k="Latest stable">{show(check.latest)}</Row>
          <Row k="Update channel">
            {show(check.channel)}
            {check.channel_changed_from ? ` (was ${check.channel_changed_from})` : ''}
          </Row>
          <Row k="Result">
            <span className={`badge badge-${state.level}`}>{state.text}</span>
          </Row>
          {check.state === 'error' && check.status && <p className="debug">{check.status}</p>}
          {check.channel_changed_from && (
            <p className="muted small">The update channel of this router was switched to stable and stays that way.</p>
          )}

          <div className="sub">Routerboard firmware</div>
          {fw && !fw.supported && <p className="muted">This device has no Routerboard firmware.</p>}
          {fw && fw.supported && (
            <>
              <Row k="Current firmware">{show(fw.current)}</Row>
              <Row k="Available firmware">{show(fw.upgrade)}</Row>
              <Row k="Status">
                {fw.pending ? (
                  <span className="badge badge-warning">Upgrade pending</span>
                ) : (
                  <span className="badge badge-normal">Up to date</span>
                )}
              </Row>
              {fw.pending && (
                <div className="toolbar" style={{ marginTop: 8 }}>
                  {armed !== 'fw' && armed !== 'fw-reboot' && (
                    <>
                      <button className="btn secondary" disabled={busy || running} onClick={() => setArmed('fw')}>
                        Upgrade firmware
                      </button>
                      <button className="btn secondary" disabled={busy || running} onClick={() => setArmed('fw-reboot')}>
                        Upgrade firmware and reboot
                      </button>
                    </>
                  )}
                  {(armed === 'fw' || armed === 'fw-reboot') && (
                    <>
                      <button className="btn" disabled={busy} onClick={() => void upgradeFirmware(armed === 'fw-reboot')}>
                        {armed === 'fw-reboot' ? 'Confirm: upgrade and reboot' : 'Confirm: upgrade'}
                      </button>
                      <button className="btn secondary" onClick={() => setArmed(null)}>
                        Cancel
                      </button>
                    </>
                  )}
                </div>
              )}
              {message && <div className="ok-box">{message}</div>}
            </>
          )}

          {check.state === 'available' && !running && !job && (
            <>
              <div className="sub">Update RouterOS</div>
              {fw?.supported && (
                <label className="opt">
                  <input type="checkbox" checked={firmware} onChange={(e) => setFirmware(e.target.checked)} />
                  <span>
                    <strong>Also upgrade the Routerboard firmware</strong>
                    <br />
                    <span className="muted small">
                      The router upgrades its firmware by itself after booting the new RouterOS, which means one
                      extra restart.
                    </span>
                  </span>
                </label>
              )}
              <div className="toolbar">
                {armed !== 'now' && armed !== 'later' && (
                  <>
                    <button className="btn" disabled={busy} onClick={() => setArmed('now')}>
                      Update and reboot now
                    </button>
                    <button className="btn secondary" disabled={busy} onClick={() => setArmed('later')}>
                      Update, reboot later
                    </button>
                  </>
                )}
                {(armed === 'now' || armed === 'later') && (
                  <>
                    <button className="btn" disabled={busy} onClick={() => void start(armed)}>
                      {armed === 'now' ? 'Confirm: the customer goes offline for a few minutes' : 'Confirm: download now, install at next reboot'}
                    </button>
                    <button className="btn secondary" onClick={() => setArmed(null)}>
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </>
      )}

      {(job || jobId) && (
        <>
          <div className="sub">Progress</div>
          <ul className="steps">
            {(job?.steps ?? []).map((step, index) => (
              <li key={`${step.at}-${index}`}>
                <span className="t">{formatTime(step.at)}</span>
                <span>{step.text}</span>
              </li>
            ))}
            {running && (
              <li>
                <Spinner /> <span className="muted">Working…</span>
              </li>
            )}
          </ul>
          {job && job.state === 'done' && <div className="ok-box">{job.message ?? NA}</div>}
          {job && job.state === 'failed' && <div className="error-box">{job.message ?? 'The update failed'}</div>}
        </>
      )}
    </>
  )
}
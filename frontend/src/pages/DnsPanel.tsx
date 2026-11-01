import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, toApiError } from '../api'
import type { DnsInfo } from '../actionTypes'
import { ErrorBox, Spinner } from '../ui'

export function DnsPanel({ ip, tid, canManage }: { ip: string; tid: string; canManage: boolean }) {
  const [info, setInfo] = useState<DnsInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [editing, setEditing] = useState(false)
  const [serversText, setServersText] = useState('')
  const [allowRemote, setAllowRemote] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<DnsInfo>('/api/router/dns/get', { method: 'POST', body: { ip, tid } })
      setInfo(data)
      setServersText(data.servers.join(', '))
      setAllowRemote(data.allow_remote_requests)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setLoading(false)
    }
  }, [ip, tid])

  useEffect(() => {
    void load()
  }, [load])

  async function save() {
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const servers = serversText.split(/[\s,]+/).filter(Boolean)
      const data = await api<DnsInfo>('/api/router/dns/save', {
        method: 'POST',
        body: { ip, tid, servers, allow_remote_requests: allowRemote },
      })
      setInfo(data)
      setEditing(false)
      setSaved(true)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <p>
        <Spinner /> Reading DNS settings…
      </p>
    )
  }

  const inUse = info && info.servers.length > 0 ? info.servers : info?.dynamic_servers ?? []
  const inUseSource = info && info.servers.length > 0 ? 'manual' : 'from PPPoE'

  return (
    <>
      <ErrorBox error={error} />
      {info && (
        <div className="kv">
          <div className="kv-row">
            <dt>Currently in use</dt>
            <dd>
              {inUse.length > 0 ? inUse.join(', ') : 'N/A'} <span className="muted small">({inUseSource})</span>
            </dd>
          </div>
          <div className="kv-row">
            <dt>Allow remote requests</dt>
            <dd>{info.allow_remote_requests ? 'Yes' : 'No'}</dd>
          </div>
        </div>
      )}
      {canManage && !editing && (
        <button className="btn secondary" style={{ marginTop: 8 }} onClick={() => setEditing(true)}>
          Edit DNS settings
        </button>
      )}
      {canManage && editing && (
        <div className="q-form" style={{ marginTop: 10 }}>
          <label className="field">
            Manual DNS servers (comma separated; leave empty to use the PPPoE-provided ones)
            <input value={serversText} onChange={(e) => setServersText(e.target.value)} placeholder="8.8.8.8, 1.1.1.1" />
          </label>
          <label className="toggle-row">
            <input type="checkbox" checked={allowRemote} onChange={(e) => setAllowRemote(e.target.checked)} />
            <span>Allow remote requests</span>
          </label>
          <div className="toolbar">
            <button className="btn" disabled={busy} onClick={() => void save()}>
              {busy ? <Spinner /> : 'Save'}
            </button>
            <button className="btn secondary" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {saved && <div className="ok-box">DNS settings saved.</div>}
    </>
  )
}
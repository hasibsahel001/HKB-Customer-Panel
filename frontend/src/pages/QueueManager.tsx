import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, api, toApiError } from '../api'
import { formatBps } from '../format'
import { RATE_PRESETS, autoQueueName, chunk, queueMatchesIp } from '../queueUtil'
import type { RouterQueue } from '../types'
import { ErrorBox, Spinner } from '../ui'

function limitText(q: RouterQueue): string {
  if (q.max_up_bps === null && q.max_down_bps === null) return 'Unlimited'
  if (q.max_up_bps === q.max_down_bps) return formatBps(q.max_up_bps)
  return `${formatBps(q.max_up_bps)} / ${formatBps(q.max_down_bps)}`
}

interface Form {
  id: string | null
  name: string
  targets: string
  up: string
  down: string
  disabled: boolean
}

function newForm(focusIp?: string): Form {
  return {
    id: null,
    name: focusIp ? autoQueueName(focusIp) : '',
    targets: focusIp ?? '',
    up: '2M',
    down: '2M',
    disabled: false,
  }
}

function formOf(q: RouterQueue): Form {
  return {
    id: q.id,
    name: q.name,
    targets: q.targets.join('\n'),
    up: q.max_up,
    down: q.max_down,
    disabled: q.disabled,
  }
}

function payload(ip: string, tid: string, form: Form) {
  return {
    ip,
    tid,
    id: form.id,
    name: form.name.trim(),
    targets: form.targets.split(/[\s,]+/).filter(Boolean),
    max_up: form.up.trim(),
    max_down: form.down.trim(),
    disabled: form.disabled,
  }
}

/** The edit screen. It replaces the list inside the same panel instead of opening another popup. */
function QueueEditor({
  ip,
  tid,
  initial,
  focusIp,
  onBack,
  onChanged,
}: {
  ip: string
  tid: string
  initial: Form
  focusIp?: string
  onBack: () => void
  onChanged: () => void
}) {
  const [form, setForm] = useState<Form>(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const creating = form.id === null
  // For one device the name and target are filled in automatically; otherwise they are needed.
  const advancedOpen = creating && !focusIp

  function setBoth(rate: string) {
    setForm({ ...form, up: rate, down: rate })
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await api('/api/router/queues/save', { method: 'POST', body: payload(ip, tid, form) })
      onChanged()
    } catch (e) {
      setError(toApiError(e))
      setBusy(false)
    }
  }

  async function remove() {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    if (!form.id) return
    setBusy(true)
    setError(null)
    try {
      await api('/api/router/queues/delete', { method: 'POST', body: { ip, tid, ids: [form.id] } })
      onChanged()
    } catch (e) {
      setError(toApiError(e))
      setConfirmDelete(false)
      setBusy(false)
    }
  }

  const same = form.up === form.down
  const valid = form.name.trim() !== '' && form.targets.trim() !== ''

  return (
    <div className="qm">
      <button className="qm-back" onClick={onBack} disabled={busy}>
        ← Back
      </button>
      <h3 className="qm-title">{creating ? 'New speed limit' : form.name}</h3>
      <ErrorBox error={error} />

      <div className="qm-label">Speed</div>
      <div className="qm-chips">
        {RATE_PRESETS.map((rate) => (
          <button
            key={rate}
            type="button"
            className={`qm-chip${same && form.up === rate ? ' on' : ''}`}
            onClick={() => setBoth(rate)}
          >
            {rate}
          </button>
        ))}
      </div>
      <div className="qm-two">
        <label className="field">
          Download
          <input value={form.down} onChange={(e) => setForm({ ...form, down: e.target.value })} />
        </label>
        <label className="field">
          Upload
          <input value={form.up} onChange={(e) => setForm({ ...form, up: e.target.value })} />
        </label>
      </div>

      <label className="toggle-row">
        <input
          type="checkbox"
          checked={!form.disabled}
          onChange={(e) => setForm({ ...form, disabled: !e.target.checked })}
        />
        <span>{form.disabled ? 'Disabled' : 'Enabled'}</span>
      </label>

      <details className="qm-adv" open={advancedOpen}>
        <summary>Name and targets</summary>
        <label className="field">
          Name
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="field">
          Targets (one IP or network per line)
          <textarea
            value={form.targets}
            onChange={(e) => setForm({ ...form, targets: e.target.value })}
            placeholder={'10.10.10.5\n10.10.10.0/24'}
          />
        </label>
      </details>

      <div className="qm-actions">
        <button className="btn" disabled={busy || !valid} onClick={() => void save()}>
          {busy ? <Spinner /> : creating ? 'Create' : 'Save'}
        </button>
        {!creating && (
          <button className="btn secondary danger" disabled={busy} onClick={() => void remove()}>
            {confirmDelete ? 'Click again to delete' : 'Delete'}
          </button>
        )}
      </div>
    </div>
  )
}

export function QueueManager({ ip, tid, focusIp }: { ip: string; tid: string; focusIp?: string }) {
  const [queues, setQueues] = useState<RouterQueue[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [editing, setEditing] = useState<Form | null>(null)
  const [showAll, setShowAll] = useState(!focusIp)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<{ queues: RouterQueue[] }>('/api/router/queues/list', {
        method: 'POST',
        body: { ip, tid },
      })
      setQueues(data.queues)
      setSelected(new Set())
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setLoading(false)
    }
  }, [ip, tid])

  useEffect(() => {
    void load()
  }, [load])

  const forDevice = useMemo(
    () => (focusIp ? queues.filter((q) => queueMatchesIp(q.targets, focusIp)) : []),
    [queues, focusIp],
  )

  const visible = useMemo(() => {
    const base = focusIp && !showAll ? forDevice : queues
    const q = search.trim().toLowerCase()
    if (!q) return base
    return base.filter((item) => [item.name, ...item.targets].some((v) => v.toLowerCase().includes(q)))
  }, [queues, forDevice, focusIp, showAll, search])

  const allSelected = visible.length > 0 && visible.every((q) => selected.has(q.id))

  function toggle(id: string) {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
    setConfirmDelete(false)
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(visible.map((q) => q.id)))
    setConfirmDelete(false)
  }

  async function deleteSelected() {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setBusy(true)
    setError(null)
    try {
      for (const ids of chunk([...selected], 200)) {
        await api('/api/router/queues/delete', { method: 'POST', body: { ip, tid, ids } })
      }
      setConfirmDelete(false)
      await load()
    } catch (e) {
      setError(toApiError(e))
      await load()
    } finally {
      setBusy(false)
    }
  }

  async function quickCreate(rate: string) {
    if (!focusIp) return
    setBusy(true)
    setError(null)
    try {
      await api('/api/router/queues/save', {
        method: 'POST',
        body: payload(ip, tid, { ...newForm(focusIp), up: rate, down: rate }),
      })
      await load()
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  function afterEdit() {
    setEditing(null)
    void load()
  }

  if (editing) {
    return (
      <QueueEditor
        ip={ip}
        tid={tid}
        initial={editing}
        focusIp={focusIp}
        onBack={() => setEditing(null)}
        onChanged={afterEdit}
      />
    )
  }

  const deviceMode = !!focusIp && !showAll
  const noQueueForDevice = deviceMode && !loading && forDevice.length === 0 && !search

  return (
    <div className="qm">
      {focusIp && (
        <div className="qm-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={!showAll}
            className={!showAll ? 'on' : ''}
            onClick={() => setShowAll(false)}
          >
            This device
          </button>
          <button role="tab" aria-selected={showAll} className={showAll ? 'on' : ''} onClick={() => setShowAll(true)}>
            All queues{queues.length > 0 ? ` (${queues.length})` : ''}
          </button>
        </div>
      )}
      <ErrorBox error={error} />
      {loading && (
        <p>
          <Spinner /> Loading…
        </p>
      )}

      {noQueueForDevice && (
        <div className="qm-empty">
          <p>
            <strong className="mono">{focusIp}</strong> has no speed limit.
          </p>
          <div className="qm-chips">
            {RATE_PRESETS.map((rate) => (
              <button key={rate} className="qm-chip" disabled={busy} onClick={() => void quickCreate(rate)}>
                {busy ? '…' : rate}
              </button>
            ))}
          </div>
          <button className="link-btn" onClick={() => setEditing(newForm(focusIp))}>
            Custom speed…
          </button>
        </div>
      )}

      {!loading && !noQueueForDevice && (
        <>
          <div className="qm-bar">
            {(queues.length > 6 || search) && (
              <input
                className="qm-search"
                placeholder="Search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search queues"
              />
            )}
            <button className="btn secondary" onClick={toggleAll} disabled={visible.length === 0 || busy}>
              {allSelected ? 'Clear selection' : 'Select all'}
            </button>
            {selected.size > 0 && (
              <button className="btn secondary danger" onClick={() => void deleteSelected()} disabled={busy}>
                {busy ? <Spinner /> : confirmDelete ? `Click again: delete ${selected.size}` : `Delete selected (${selected.size})`}
              </button>
            )}
            <button className="btn qm-add" onClick={() => setEditing(newForm(focusIp))} disabled={busy}>
              + Add
            </button>
          </div>

          <div className="q-list qm-list">
            {visible.map((q) => (
              <div key={q.id} className={`qm-row${selected.has(q.id) ? ' sel' : ''}`}>
                <input
                  type="checkbox"
                  checked={selected.has(q.id)}
                  onChange={() => toggle(q.id)}
                  aria-label={`Select ${q.name}`}
                />
                <button className="qm-row-main" onClick={() => setEditing(formOf(q))}>
                  <span className="qm-name">{q.name}</span>
                  <span className="qm-target muted small">
                    {q.targets[0] ?? '—'}
                    {q.targets.length > 1 && ` +${q.targets.length - 1}`}
                  </span>
                  <span className="qm-limit num">{limitText(q)}</span>
                  {q.disabled && <span className="badge badge-unknown">Off</span>}
                </button>
              </div>
            ))}
            {visible.length === 0 && (
              <p className="muted">{search ? 'No queue matches your search.' : 'This router has no simple queues.'}</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
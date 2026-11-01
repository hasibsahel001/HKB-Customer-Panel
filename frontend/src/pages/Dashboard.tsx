import { useMemo, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import type { CSSProperties } from 'react'
import { useAuth } from '../auth'
import { canCopyImage, copyImage, copyText } from '../clipboard'
import { deviceName } from '../devices'
import { formatBps, show } from '../format'
import { buildOnlineModel, renderOnlineImage } from '../onlineImage'
import type { DeviceItem, Diagnostics, Report } from '../types'
import type { LiveDevicesState } from '../useLiveDevices'
import { Dot, Modal, StatusBadge, levelKey } from '../ui'
import { QueueManager } from './QueueManager'
import { NoData, dataOf, limitText } from './shared'
import type { LiveState } from './shared'
import { TileModal, Tiles } from './Tiles'
import type { Open } from './Tiles'

const OVERALL_WORD: Record<string, string> = {
  normal: 'All good',
  warning: 'Needs a look',
  serious: 'Problem',
  critical: 'Critical',
  unknown: 'Unverified',
}

export function CustomerHero({ report, overall }: { report: Report; overall: string }) {
  const pppoe = dataOf(report.sections.pppoe)
  const identity = dataOf(report.sections.identity)
  const resource = dataOf(report.sections.resource)
  const username = pppoe?.username ?? null
  const key = levelKey(overall)
  const letter = (username ?? identity?.identity ?? '?').slice(0, 1).toUpperCase()

  return (
    <section className="hero rise">
      <div className="hero-avatar">{letter}</div>
      <div className="hero-main">
        <div className="hero-name">{username ?? 'PPPoE user not available'}</div>
        <div className="hero-sub">
          Device {show(identity?.identity)} · {show(resource?.model)} · RouterOS {show(resource?.version)}
        </div>
        {report.connected_with_account !== 0 && (
          <div className="hero-warn">
            Logged in with fallback account #{report.connected_with_account}; the Technical ID is not confirmed
            by the login.
          </div>
        )}
      </div>
      <div className="hero-pills">
        <span className="pill mono">{report.ip}</span>
        <span className={`pill status s-${key}`}>
          <Dot level={key} />
          {OVERALL_WORD[key]}
        </span>
      </div>
    </section>
  )
}

type SortKey = 'host' | 'ip' | 'queue'

const SCOPE_ORDER: Record<string, number> = { own: 0, shared: 1, none: 2, unknown: 3 }

function ipKey(ip: string): number {
  return ip.split('.').reduce((acc, part) => acc * 256 + (parseInt(part, 10) || 0), 0)
}

function sortValue(d: DeviceItem, key: SortKey): number | string {
  if (key === 'ip') return ipKey(d.ip)
  if (key === 'host') return deviceName(d.hostname, d.mac_address).text.toLowerCase()
  return `${SCOPE_ORDER[d.queue_scope] ?? 9}${(d.queue_names[0] ?? '').toLowerCase()}`
}

function QueueCell({ d }: { d: DeviceItem }) {
  if (d.queue_scope === 'unknown') return <span className="muted">Unknown</span>
  if (d.queue_scope === 'none') {
    return (
      <span>
        <span className="qtag q-free">Free</span>
        <span className="muted">no queue</span>
      </span>
    )
  }
  const limit = limitText(d.queue_limit_upload_bps, d.queue_limit_download_bps)
  if (d.queue_scope === 'own') {
    return (
      <span>
        <span className="qtag q-own">Limited</span>
        <strong className="num">{limit}</strong>
      </span>
    )
  }
  return (
    <span>
      <span className="qtag q-shared">Shared queue</span>
      {d.queue_ambiguous ? (
        <span className="muted">limit unclear</span>
      ) : (
        <strong className="num">{limit}</strong>
      )}
    </span>
  )
}

function DevicesCard({
  report,
  debug,
  liveDevices,
}: {
  report: Report
  debug: boolean
  liveDevices: LiveDevicesState
}) {
  const { can } = useAuth()
  const section = report.sections.devices
  const data = liveDevices.data ?? dataOf(section)
  const [key, setKey] = useState<SortKey>('ip')
  const [asc, setAsc] = useState(true)
  const [queueTarget, setQueueTarget] = useState<string | null>(null)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [imageNote, setImageNote] = useState('')
  const manageable = can('router.manage')

  const rows = useMemo(() => {
    if (!data) return []
    return [...data.devices].sort((a, b) => {
      const x = sortValue(a, key)
      const y = sortValue(b, key)
      const result = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      return asc ? result : -result
    })
  }, [data, key, asc])

  async function copyName(event: MouseEvent, text: string, rowKey: string) {
    event.stopPropagation() // copying the name must not open the speed-limit popup
    if (!(await copyText(text))) return
    setCopiedKey(rowKey)
    clearTimeout(copiedTimer.current)
    copiedTimer.current = setTimeout(() => setCopiedKey(null), 1200)
  }

  function sortBy(next: SortKey) {
    if (next === key) setAsc(!asc)
    else {
      setKey(next)
      setAsc(true)
    }
  }

  function head(label: string, next: SortKey) {
    return (
      <th className="sortable" onClick={() => sortBy(next)}>
        {label} {key === next ? (asc ? '▲' : '▼') : ''}
      </th>
    )
  }

  const traffic = data?.total_traffic ?? null

  async function copyPicture() {
    if (!data) return
    setImageNote('')
    try {
      const username = dataOf(report.sections.pppoe)?.username ?? null
      const blob = await renderOnlineImage(buildOnlineModel({ username, data, now: new Date() }))
      const ok = await copyImage(blob)
      setImageNote(ok ? 'Copied' : 'Needs HTTPS or localhost')
    } catch {
      setImageNote('Failed')
    }
    setTimeout(() => setImageNote(''), 2500)
  }

  return (
    <section className="card rise" style={{ '--i': 4 } as CSSProperties}>
      <div className="d-head">
        <h2>Devices online{data ? ` (${data.count})` : ''}</h2>
        {liveDevices.data && (
          <span
            className={`live-dot ${liveDevices.ok ? 'on' : 'off'}`}
            title={liveDevices.ok ? 'Updating live (about every second)' : 'Live updates paused: connection problem'}
          >
            {liveDevices.ok ? 'Live' : 'Paused'}
          </span>
        )}
        {traffic && (
          <div className="traffic-now" title={`Single sample on ${traffic.interface}`}>
            <span className="up">↑ {formatBps(traffic.upload_bps)}</span>
            <span className="down">↓ {formatBps(traffic.download_bps)}</span>
          </div>
        )}
        {data && (
          <button
            className="btn secondary small-btn"
            onClick={() => void copyPicture()}
            disabled={!canCopyImage()}
            title={canCopyImage() ? 'Copy a picture of the online devices' : 'Copying a picture needs HTTPS or localhost'}
          >
            {imageNote || 'Copy image'}
          </button>
        )}
      </div>
      {!data && <NoData section={section} debug={debug} />}
      {data && (
        <div className="t-scroll">
          <table className="dev-table">
            <thead>
              <tr>
                {head('Host', 'host')}
                {head('IP', 'ip')}
                <th>MAC</th>
                {head('Speed limit', 'queue')}
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const name = deviceName(d.hostname, d.mac_address)
                const rowKey = `${d.ip}-${d.mac_address}`
                return (
                  <tr
                    key={rowKey}
                    className={manageable ? 'clickable-row' : undefined}
                    onClick={() => manageable && setQueueTarget(d.ip)}
                    title={manageable ? "Click to manage this device's speed limit" : undefined}
                  >
                    <td className={name.named ? '' : 'muted'}>
                      <button
                        type="button"
                        className="copy-name"
                        title="Click to copy the name"
                        onClick={(event) => void copyName(event, name.text, rowKey)}
                      >
                        {name.text}
                      </button>
                      {copiedKey === rowKey && <span className="copied-tag">Copied</span>}
                    </td>
                    <td className="mono">{d.ip}</td>
                    <td className="mono muted small">{d.mac_address}</td>
                    <td>
                      <QueueCell d={d} />
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted">
                    No active devices.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {queueTarget && (
        <Modal title={`Speed limit: ${queueTarget}`} onClose={() => setQueueTarget(null)} strict>
          <QueueManager ip={report.ip} tid={report.technical_id} focusIp={queueTarget} />
        </Modal>
      )}
    </section>
  )
}

function FindingsCard({ diagnostics, liveLoading }: { diagnostics: Diagnostics; liveLoading: boolean }) {
  return (
    <section className="card rise" style={{ '--i': 5 } as CSSProperties}>
      <div className="d-head">
        <h2>Findings ({diagnostics.findings.length})</h2>
        <StatusBadge level={diagnostics.overall} />
      </div>
      <div className="findings fa">
        {diagnostics.error && <p className="muted">تشخیص‌ها تولید نشد.</p>}
        {!diagnostics.error && diagnostics.findings.length === 0 && (
          <p className="muted">
            {liveLoading ? 'در حال اندازه‌گیری پینگ…' : 'با داده‌هایی که خوانده شد مشکلی تشخیص داده نشد.'}
          </p>
        )}
        {diagnostics.findings.map((finding) => (
          <details key={`${finding.code}-${JSON.stringify(finding.evidence)}`} className="f">
            <summary>
              <Dot level={finding.severity} />
              <span>{finding.title}</span>
            </summary>
            <div className="f-body">
              {finding.suggested_action && (
                <div>
                  <strong>اقدام پیشنهادی:</strong> {finding.suggested_action}
                </div>
              )}
              {finding.probable_causes.length > 0 && (
                <>
                  <div className="lbl">علت‌های احتمالی</div>
                  <ul>
                    {finding.probable_causes.map((cause) => (
                      <li key={cause}>{cause}</li>
                    ))}
                  </ul>
                </>
              )}
              {Object.keys(finding.evidence).length > 0 && (
                <>
                  <div className="lbl">شواهد</div>
                  <ul className="mono small ev">
                    {Object.entries(finding.evidence).map(([name, value]) => (
                      <li key={name}>
                        {name}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </details>
        ))}
      </div>
    </section>
  )
}

export function DashboardSkeleton() {
  return (
    <div className="dash">
      <div className="tiles">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton" />
        ))}
      </div>
      <div className="d-left">
        <div className="skeleton" style={{ minHeight: 280 }} />
      </div>
      <div className="d-right">
        <div className="skeleton" style={{ minHeight: 280 }} />
      </div>
    </div>
  )
}

export function Dashboard({
  report,
  live,
  liveDevices,
  diagnostics,
  debug,
}: {
  report: Report
  live: LiveState
  liveDevices: LiveDevicesState
  diagnostics: Diagnostics
  debug: boolean
}) {
  const [open, setOpen] = useState<Open>(null)
  const [dnsVersion, setDnsVersion] = useState(0)
  function closeTile() {
    setOpen(null)
    setDnsVersion((v) => v + 1) // the DNS settings may have been edited in the popup
  }
  return (
    <div className="dash">
      <Tiles
        report={report}
        live={live}
        debug={debug}
        onOpen={setOpen}
        dnsVersion={dnsVersion}
        liveWireless={liveDevices.data?.wireless ?? null}
      />
      <div className="d-left">
        <DevicesCard report={report} debug={debug} liveDevices={liveDevices} />
      </div>
      <div className="d-right">
        <FindingsCard diagnostics={diagnostics} liveLoading={live.loading} />
      </div>
      {open && (
        <TileModal
          open={open}
          report={report}
          live={live}
          debug={debug}
          onClose={closeTile}
          liveWireless={liveDevices.data?.wireless ?? null}
        />
      )}
    </div>
  )
}
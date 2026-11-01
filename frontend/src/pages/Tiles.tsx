import { useEffect, useState } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyEvent, ReactNode } from 'react'
import { api } from '../api'
import type { DnsInfo } from '../actionTypes'
import { NA, compactDuration, formatBytes, rateMbps, show } from '../format'
import { useAuth } from '../auth'
import { mergeLiveWireless } from '../liveWireless'
import type { LiveWireless } from '../liveWireless'
import type { PingData, PingEntry, Report } from '../types'
import { Dot, Modal, StatusBadge, levelKey } from '../ui'
import { DnsPanel } from './DnsPanel'
import { Gauge, NoData, Row, dataOf, ms, pair, signalPct } from './shared'
import type { LiveState } from './shared'

export type Open = 'pppoe' | 'wireless' | 'internet' | 'lan' | null

const WORD: Record<string, string> = {
  normal: 'OK',
  warning: 'Warning',
  serious: 'Serious',
  critical: 'Critical',
  unknown: 'Unknown',
}

function Tile({
  title,
  icon,
  hue,
  index,
  level,
  onOpen,
  children,
}: {
  title: string
  icon: string
  hue: string
  index: number
  level: string
  onOpen: () => void
  children: ReactNode
}) {
  const key = levelKey(level)
  const style = { '--hue': hue, '--i': index } as CSSProperties
  function onKey(event: ReactKeyEvent) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onOpen()
    }
  }
  return (
    <section
      className={`tile rise l-${key}`}
      style={style}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={onKey}
      aria-label={`${title}: open details`}
    >
      <div className="t-head">
        <span className="t-icon" aria-hidden="true">
          {icon}
        </span>
        <span className="t-title">{title}</span>
        <span className="t-state">
          <Dot level={key} />
          {WORD[key]}
        </span>
      </div>
      {children}
      <span className="corner" aria-hidden="true" />
    </section>
  )
}

function bestTarget(ping: PingData | null): PingEntry | null {
  if (!ping) return null
  const reachable = ping.targets.filter((t) => t.reachable)
  if (reachable.length === 0) return ping.targets[0] ?? null
  return [...reachable].sort(
    (a, b) => (a.summary?.avg_ms ?? Infinity) - (b.summary?.avg_ms ?? Infinity),
  )[0]
}

function lanVerdict(running: boolean | null, rate: string | null, fullDuplex: boolean | null) {
  if (running === false) return { level: 'critical', text: 'Link down: check the cable and the device behind it' }
  if (running === null) return { level: 'unknown', text: 'Link state unknown' }
  const mbps = rateMbps(rate)
  if ((mbps !== null && mbps < 100) || fullDuplex === false) {
    return { level: 'warning', text: 'Link is slower than expected: check the cable' }
  }
  return { level: 'normal', text: 'Link looks healthy' }
}

function PingDetails({ entry }: { entry: PingEntry }) {
  const s = entry.summary
  return (
    <>
      <div className="sub">{entry.host}</div>
      {s ? (
        <>
          <Row k="Sent / received">
            {show(s.sent)} / {show(s.received)}
          </Row>
          <Row k="Packet loss">{show(s.loss_percent, '%')}</Row>
          <Row k="Min / avg / max">
            {ms(s.min_ms)} / {ms(s.avg_ms)} / {ms(s.max_ms)}
          </Row>
        </>
      ) : (
        <p className="muted">No reply data.</p>
      )}
    </>
  )
}

/** Reads the router's DNS settings once for the tile (and again when `version` changes). */
function useDnsSummary(ip: string, tid: string, enabled: boolean, version: number) {
  const [info, setInfo] = useState<DnsInfo | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (!enabled) return
    let stopped = false
    setFailed(false)
    api<DnsInfo>('/api/router/dns/get', { method: 'POST', body: { ip, tid } })
      .then((data) => !stopped && setInfo(data))
      .catch(() => !stopped && setFailed(true))
    return () => {
      stopped = true
    }
  }, [ip, tid, enabled, version])
  return { info, failed }
}

function UptimeRow({ label, value, sub, state }: { label: string; value: string; sub?: string; state?: string }) {
  return (
    <div className="up-row">
      <span className={`up-dot ${state ?? 'unknown'}`} aria-hidden="true" />
      <span className="up-label">{label}</span>
      {sub && <span className="up-sub mono">{sub}</span>}
      <span className="up-value">{value}</span>
    </div>
  )
}

export function Tiles({
  report,
  live,
  debug,
  onOpen,
  dnsVersion = 0,
  liveWireless = null,
}: {
  report: Report
  live: LiveState
  debug: boolean
  onOpen: (tile: Open) => void
  dnsVersion?: number
  liveWireless?: LiveWireless | null
}) {
  const { can } = useAuth()
  const dns = useDnsSummary(report.ip, report.technical_id, can('router.manage'), dnsVersion)
  const pppoe = dataOf(report.sections.pppoe)
  const resource = dataOf(report.sections.resource)
  const wireless = mergeLiveWireless(dataOf(report.sections.wireless), liveWireless)
  const ether1 = dataOf(report.sections.ether1)
  const ping = live.data && live.data.ping.ok ? live.data.ping.data : null
  const probe = live.data?.ap_probe && live.data.ap_probe.ok ? live.data.ap_probe.data : null
  const reg = wireless?.registration ?? null
  const radio = reg?.radio_name ?? null
  const analysis = wireless?.analysis

  const connected = pppoe ? (pppoe.status === null ? pppoe.running : pppoe.status === 'connected') : null
  const pppoeLevel = connected === true ? 'normal' : connected === false ? 'critical' : 'unknown'
  const pppoeWord = connected === true ? 'Connected' : connected === false ? 'Disconnected' : NA

  const wirelessLevel = wireless
    ? wireless.registration_count === 0 || !reg
      ? 'critical'
      : wireless.analysis.overall
    : 'unknown'

  const internet = bestTarget(ping)
  const internetLevel = live.loading
    ? 'unknown'
    : internet && internet.reachable
      ? internet.status
      : ping?.layers.internet_reachable === false
        ? 'critical'
        : 'unknown'
  let internetMain = NA
  let internetSub = ''
  if (live.loading) internetMain = 'Measuring…'
  else if (internet?.reachable === false) internetMain = 'No reply'
  else if (internet?.summary) {
    internetMain = ms(internet.summary.avg_ms)
    internetSub = `${internet.host} · ${internet.summary.loss_percent ?? 0}% packet loss`
  }

  const foundPeers = probe ? probe.peers.filter((p) => p.reachable) : []
  let apIps = NA
  if (live.loading) apIps = 'Looking…'
  else if (probe) apIps = foundPeers.length === 0 ? 'None found' : foundPeers.map((p) => p.ip).join(', ')

  const lan = ether1 ? lanVerdict(ether1.running ?? null, ether1.link_rate, ether1.full_duplex) : null
  const duplex =
    ether1?.full_duplex === null || ether1?.full_duplex === undefined ? '' : ether1.full_duplex ? ' · Full' : ' · Half'
  const lanMain = ether1
    ? ether1.running
      ? `${ether1.link_rate ?? 'Up'}${duplex}`
      : ether1.running === false
        ? 'Link down'
        : NA
    : NA

  return (
    <div className="tiles">
      <Tile title="Service uptime" icon="🔗" hue="#8b5cf6" index={0} level={pppoeLevel} onOpen={() => onOpen('pppoe')}>
        <div className="up-rows">
          <UptimeRow
            label="PPPoE"
            value={compactDuration(pppoe?.uptime)}
            sub={pppoeWord}
            state={connected === true ? 'normal' : connected === false ? 'critical' : 'unknown'}
          />
          <UptimeRow
            label="Wireless"
            value={compactDuration(reg?.uptime)}
            sub={radio ?? undefined}
            state={wireless ? (reg ? 'normal' : 'critical') : 'unknown'}
          />
          <UptimeRow label="Device" value={compactDuration(resource?.uptime)} state={resource ? 'normal' : 'unknown'} />
        </div>
      </Tile>

      <Tile title="Wireless" icon="📡" hue="#3b82f6" index={1} level={wirelessLevel} onOpen={() => onOpen('wireless')}>
        {!wireless && <NoData section={report.sections.wireless} debug={debug} />}
        {wireless && !reg && <div className="t-main">Not registered</div>}
        {wireless && reg && (
          <>
            <div className="t-sub">
              Remote radio
              {liveWireless && (
                <span className="live-dot on live-tag" title="Signal and CCQ update about every second">
                  Live
                </span>
              )}
            </div>
            <div className="t-main grad mono" title={radio ?? ''}>
              {radio ?? NA}
            </div>
            <Gauge
              label="Signal"
              value={show(reg.signal_dbm, ' dBm')}
              pct={signalPct(reg.signal_dbm)}
              level={analysis?.signal}
            />
            {reg.chains.map((c) => (
              <Gauge
                key={c.chain}
                label={`Tx/Rx signal Ch${c.chain}`}
                value={`${pair(c.tx_dbm, c.rx_dbm)} dBm`}
                pct={signalPct(
                  c.tx_dbm !== null && c.rx_dbm !== null ? (c.tx_dbm + c.rx_dbm) / 2 : (c.tx_dbm ?? c.rx_dbm),
                )}
                level={analysis?.chains?.find((x) => x.chain === c.chain)?.level}
              />
            ))}
            <Gauge label="CCQ Tx" value={show(reg.tx_ccq, '%')} pct={reg.tx_ccq} level={analysis?.ccq_tx} />
            <Gauge label="CCQ Rx" value={show(reg.rx_ccq, '%')} pct={reg.rx_ccq} level={analysis?.ccq_rx} />
            <Row k="SNR">{show(reg.snr_db, ' dB')}</Row>
          </>
        )}
      </Tile>

      <Tile title="Internet & DNS" icon="🌐" hue="#06b6d4" index={2} level={internetLevel} onOpen={() => onOpen('internet')}>
        <div className="t-main">{internetMain}</div>
        <div className="t-sub">{internetSub || (live.loading ? 'Pinging from the customer router' : ' ')}</div>
        <Row k="Customer AP IP">
          <span className="mono">{apIps}</span>
        </Row>
        {live.failed && <p className="muted">The measurement could not be completed.</p>}
        {can('router.manage') && (
          <div className="dns-box">
            <Row k="DNS">
              {dns.info ? (
                <span className="mono">
                  {dns.info.servers.length > 0
                    ? dns.info.servers.join(', ')
                    : dns.info.dynamic_servers.length > 0
                      ? `${dns.info.dynamic_servers.join(', ')} (from PPPoE)`
                      : 'None'}
                </span>
              ) : dns.failed ? (
                <span className="muted">Unavailable</span>
              ) : (
                <span className="muted">Reading…</span>
              )}
            </Row>
            <Row k="Allow remote requests">
              {dns.info ? (
                <span className={dns.info.allow_remote_requests ? 'flag-on' : 'flag-off'}>
                  {dns.info.allow_remote_requests ? 'Yes' : 'No'}
                </span>
              ) : (
                <span className="muted">{dns.failed ? 'Unavailable' : '…'}</span>
              )}
            </Row>
          </div>
        )}
      </Tile>

      <Tile title="LAN port" icon="🔌" hue="#14b8a6" index={3} level={lan?.level ?? 'unknown'} onOpen={() => onOpen('lan')}>
        {!ether1 && <NoData section={report.sections.ether1} debug={debug} />}
        {ether1 && (
          <>
            <div className="t-sub">ether1</div>
            <div className="t-main">{lanMain}</div>
            <Row k="Link downs (since boot)">{show(ether1.link_downs)}</Row>
            {lan && <div className="verdict-line">{lan.text}</div>}
          </>
        )}
      </Tile>
    </div>
  )
}

export function TileModal({
  open,
  report,
  live,
  debug,
  onClose,
  liveWireless = null,
}: {
  open: Exclude<Open, null>
  report: Report
  live: LiveState
  debug: boolean
  onClose: () => void
  liveWireless?: LiveWireless | null
}) {
  const { can } = useAuth()
  const pppoe = dataOf(report.sections.pppoe)
  const resource = dataOf(report.sections.resource)
  const wireless = mergeLiveWireless(dataOf(report.sections.wireless), liveWireless)
  const ether1 = dataOf(report.sections.ether1)
  const ping = live.data && live.data.ping.ok ? live.data.ping.data : null
  const probe = live.data?.ap_probe && live.data.ap_probe.ok ? live.data.ap_probe.data : null
  const reg = wireless?.registration ?? null

  if (open === 'pppoe') {
    return (
      <Modal title="Service uptime" onClose={onClose}>
        {!pppoe ? (
          <NoData section={report.sections.pppoe} debug={debug} />
        ) : (
          <>
            <Row k="PPPoE username">{show(pppoe.username)}</Row>
            <Row k="Status">{show(pppoe.status)}</Row>
            <Row k="PPPoE interface">{show(pppoe.name)}</Row>
            <Row k="Runs over">{show(pppoe.underlying_interface)}</Row>
            <Row k="Local IP">
              <span className="mono">{show(pppoe.local_address)}</span>
            </Row>
            <Row k="Matches the entered IP">
              {pppoe.matches_panel_ip === null ? NA : pppoe.matches_panel_ip ? 'Yes' : 'No'}
            </Row>
            <div className="sub">Uptime</div>
            <Row k="PPPoE service">{compactDuration(pppoe.uptime)}</Row>
            <Row k="Wireless link">{compactDuration(reg?.uptime)}</Row>
            <Row k="Device">{compactDuration(resource?.uptime)}</Row>
            <div className="sub">Router</div>
            <Row k="CPU load">{show(resource?.cpu_load, '%')}</Row>
            <Row k="RAM used">{show(resource?.ram_used_percent, '%')}</Row>
            {pppoe.client_count > 1 && (
              <p className="muted small">{pppoe.client_count} PPPoE clients exist; the first enabled one is shown.</p>
            )}
          </>
        )}
      </Modal>
    )
  }

  if (open === 'wireless') {
    return (
      <Modal title="Wireless link" onClose={onClose}>
        {!wireless ? (
          <NoData section={report.sections.wireless} debug={debug} />
        ) : (
          <>
            <Row k="Overall">
              <StatusBadge level={wireless.analysis.overall} />
            </Row>
            <Row k="Remote radio">{show(reg?.radio_name)}</Row>
            <Row k="Remote MAC">
              <span className="mono">{show(reg?.mac_address)}</span>
            </Row>
            <div className="sub">Signal</div>
            <Row k="Combined signal">
              <Dot level={wireless.analysis.signal} />
              {show(reg?.signal_dbm, ' dBm')}
            </Row>
            {(reg?.chains ?? []).map((c) => (
              <Row key={c.chain} k={`Tx/Rx signal Ch${c.chain}`}>
                <Dot level={wireless.analysis.chains?.find((x) => x.chain === c.chain)?.level} />
                <span className="mono">{pair(c.tx_dbm, c.rx_dbm)} dBm</span>
              </Row>
            ))}
            <Row k="SNR">{show(reg?.snr_db, ' dB')}</Row>
            <Row k="Noise floor (derived)">{show(reg?.noise_floor_dbm, ' dBm')}</Row>
            <div className="sub">Quality</div>
            <Row k="CCQ Tx">
              <Dot level={wireless.analysis.ccq_tx} />
              {show(reg?.tx_ccq, '%')}
            </Row>
            <Row k="CCQ Rx">
              <Dot level={wireless.analysis.ccq_rx} />
              {show(reg?.rx_ccq, '%')}
            </Row>
            <Row k="Tx rate">{show(reg?.tx_rate)}</Row>
            <Row k="Rx rate">{show(reg?.rx_rate)}</Row>
            <div className="sub">Radio</div>
            <Row k="Interface">{show(wireless.interface)}</Row>
            <Row k="SSID">{show(wireless.ssid)}</Row>
            <Row k="Frequency">{show(wireless.frequency, ' MHz')}</Row>
            <Row k="Band / width">
              {show(wireless.band)} · {show(wireless.channel_width)}
            </Row>
            {debug && reg && reg.chains.length === 0 && (wireless.debug_registration_keys ?? []).length > 0 && (
              <p className="debug">Fields: {(wireless.debug_registration_keys ?? []).join(', ')}</p>
            )}
          </>
        )}
      </Modal>
    )
  }

  if (open === 'internet') {
    return (
      <Modal title="Internet & DNS" onClose={onClose}>
        <p className="muted small">
          Pings run on the customer router. Reaching the router says nothing about the internet by itself.
        </p>
        <div className="sub">Internet</div>
        {live.loading && <p>Measuring…</p>}
        {!live.loading && (!ping || ping.targets.length === 0) && <p className="muted">No ping data.</p>}
        {ping?.targets.map((target) => <PingDetails key={target.host} entry={target} />)}
        <div className="sub">Customer AP IP</div>
        {live.loading && <p>Looking…</p>}
        {!live.loading && !probe && <p className="muted">No data.</p>}
        {probe?.peers.map((p) => (
          <Row key={p.ip} k={p.ip}>
            {p.reachable
              ? [ms(p.avg_ms), p.vendor, p.mac ?? 'MAC unknown'].filter(Boolean).join(' · ')
              : 'no answer'}
          </Row>
        ))}
        {probe && probe.found.length > 0 && (
          <p className="muted small">
            Brand names come from the MAC address. Add prefixes in backend/oui.csv to recognise more vendors.
          </p>
        )}
        <div className="sub">DNS</div>
        <DnsPanel ip={report.ip} tid={report.technical_id} canManage={can('router.manage')} />
      </Modal>
    )
  }

  return (
    <Modal title="LAN port (ether1)" onClose={onClose}>
      {!ether1 ? (
        <NoData section={report.sections.ether1} debug={debug} />
      ) : (
        <>
          <Row k="Running">{ether1.running === null ? NA : ether1.running ? 'Yes' : 'No'}</Row>
          <Row k="Link status">{show(ether1.link_status)}</Row>
          <Row k="Negotiated rate">{show(ether1.link_rate)}</Row>
          <Row k="Duplex">{ether1.full_duplex === null ? NA : ether1.full_duplex ? 'Full' : 'Half'}</Row>
          <Row k="Link downs since boot">{show(ether1.link_downs)}</Row>
          <Row k="Last link up (router time)">{show(ether1.last_link_up_time)}</Row>
          <Row k="Received total">{formatBytes(ether1.rx_bytes_total)}</Row>
          <Row k="Sent total">{formatBytes(ether1.tx_bytes_total)}</Row>
          <div className="sub">IP addresses on ether1</div>
          {(ether1.addresses ?? []).length === 0 && <p className="muted">No addresses were read.</p>}
          {(ether1.addresses ?? []).map((a) => (
            <Row key={a} k="Address">
              <span className="mono">{a}</span>
            </Row>
          ))}
        </>
      )}
    </Modal>
  )
}
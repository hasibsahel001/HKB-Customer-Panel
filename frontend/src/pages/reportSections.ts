import { rateMbps } from '../format'
import { colorForLevel } from '../reportImage'
import type { ReportRow, ReportSection } from '../reportImage'
import { mergeLiveWireless } from '../liveWireless'
import type { LiveWireless } from '../liveWireless'
import type { LiveResult, Report } from '../types'
import { dataOf, pair } from './shared'

const GOOD = '#059669'
const BAD = '#dc2626'
const NA = 'N/A'

/** The PPPoE username of the customer, or null when the router has none. */
export function reportUsername(report: Report): string | null {
  return dataOf(report.sections.pppoe)?.username ?? null
}

/** Remote radio, signal per chain, CCQ, SNR, noise floor and frequency. */
export function signalSection(report: Report, live?: LiveWireless | null): ReportSection {
  const wireless = mergeLiveWireless(dataOf(report.sections.wireless), live)
  const reg = wireless?.registration ?? null
  const analysis = wireless?.analysis

  const chainRow = (index: number): ReportRow => {
    const chain = reg?.chains.find((c) => c.chain === index)
    return {
      label: `Tx/Rx signal Ch${index}`,
      value: chain ? `${pair(chain.tx_dbm, chain.rx_dbm)} dBm` : NA,
      color: colorForLevel(analysis?.chains?.find((c) => c.chain === index)?.level ?? 'unknown'),
    }
  }

  const noise =
    reg?.noise_floor_dbm ?? (reg?.signal_dbm != null && reg?.snr_db != null ? reg.signal_dbm - reg.snr_db : null)
  const frequency = wireless?.frequency
  const ccqText =
    reg && (reg.rx_ccq != null || reg.tx_ccq != null)
      ? `Rx ${reg.rx_ccq != null ? `${reg.rx_ccq}%` : '–'} / Tx ${reg.tx_ccq != null ? `${reg.tx_ccq}%` : '–'}`
      : NA

  return {
    title: 'Signal',
    headline: { label: 'Remote radio', value: reg?.radio_name ?? NA, color: '#2563eb' },
    rows: [
      chainRow(0),
      chainRow(1),
      { label: 'CCQ (Rx / Tx)', value: ccqText, color: colorForLevel(analysis?.ccq ?? 'unknown') },
      { label: 'SNR', value: reg?.snr_db != null ? `${reg.snr_db} dB` : NA },
      { label: 'Noise floor (derived)', value: noise != null ? `${noise} dBm` : NA },
      { label: 'Frequency', value: frequency != null && frequency !== '' ? `${frequency} MHz` : NA },
    ],
  }
}

/** ether1 link state, negotiated rate, duplex and link-down count. */
export function cableSection(report: Report): ReportSection {
  const ether1 = dataOf(report.sections.ether1)
  const up = ether1?.running === true
  const mbps = rateMbps(ether1?.link_rate ?? null)
  const percent = mbps !== null ? Math.min(100, Math.round((mbps / 100) * 100)) : null
  const downs = ether1?.link_downs ?? null
  const fullDuplex = ether1?.full_duplex

  return {
    title: 'Cable',
    headline: {
      label: 'Cable link (ether1)',
      value: ether1 ? (up ? 'UP' : 'DOWN') : NA,
      color: ether1 ? (up ? GOOD : BAD) : '#64748b',
    },
    rows: [
      {
        label: 'Negotiated rate',
        value: ether1?.link_rate ?? NA,
        color: percent === 100 ? GOOD : percent !== null ? BAD : undefined,
      },
      {
        label: 'Rate vs 100 Mbps',
        value: percent !== null ? `${percent}%` : NA,
        color: percent === 100 ? GOOD : percent !== null ? BAD : undefined,
      },
      {
        label: 'Duplex',
        value: fullDuplex === null || fullDuplex === undefined ? NA : fullDuplex ? 'Full' : 'Half',
        color: fullDuplex === false ? BAD : fullDuplex === true ? GOOD : undefined,
      },
      {
        label: 'Link downs (since boot)',
        value: downs != null ? String(downs) : NA,
        color: downs != null ? (downs === 0 ? GOOD : downs >= 5 ? BAD : '#b45309') : undefined,
      },
      { label: 'Last link up (router time)', value: ether1?.last_link_up_time ?? NA },
    ],
  }
}

/** Quality of the ping to 8.8.8.8 and its packet loss, from a fresh measurement on the router. */
export function pingSection(live: LiveResult | null): ReportSection {
  const ping = live && live.ping.ok ? live.ping.data : null
  const entry = ping?.targets.find((t) => t.host === '8.8.8.8') ?? ping?.targets[0] ?? null
  const summary = entry?.summary ?? null
  const host = entry?.host ?? '8.8.8.8'

  const avg = summary?.avg_ms ?? null
  const loss = summary?.loss_percent ?? null
  const noReply = summary !== null && summary.reachable === false
  const avgColor = noReply ? BAD : avg === null ? '#64748b' : avg >= 300 ? BAD : avg >= 150 ? '#b45309' : GOOD
  const lossColor = loss === null ? undefined : loss >= 10 ? BAD : loss >= 2 ? '#b45309' : GOOD
  const msText = (v: number | null | undefined) => (v == null ? NA : v >= 10 ? `${Math.round(v)} ms` : `${v.toFixed(1)} ms`)

  return {
    title: 'Ping',
    headline: {
      label: `Ping ${host}`,
      value: noReply ? 'No reply' : avg !== null ? msText(avg) : NA,
      color: avgColor,
    },
    rows: [
      { label: 'Packet loss', value: loss !== null ? `${loss}%` : NA, color: lossColor },
      { label: 'Fastest / slowest', value: summary ? `${msText(summary.min_ms)} / ${msText(summary.max_ms)}` : NA },
      {
        label: 'Replies received',
        value: summary && summary.sent != null ? `${summary.received ?? 0} of ${summary.sent}` : NA,
      },
    ],
  }
}
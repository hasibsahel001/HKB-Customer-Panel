import type { ReactNode } from 'react'
import { NA, formatBps } from '../format'
import type { LiveResult, SectionResult } from '../types'
import { Meter } from '../ui'

export interface LiveState {
  data: LiveResult | null
  loading: boolean
  failed: boolean
}

export function dataOf<T>(section: SectionResult<T> | undefined): T | null {
  return section && section.ok ? section.data : null
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return NA
  return value >= 10 ? `${Math.round(value)} ms` : `${value.toFixed(1)} ms`
}

export function pair(a: number | null, b: number | null): string {
  return `${a === null ? '–' : a}/${b === null ? '–' : b}`
}

export function limitText(up: number | null, down: number | null): string {
  if (up === null && down === null) return 'Unlimited'
  if (up === down) return formatBps(up)
  return `${formatBps(up)} / ${formatBps(down)}`
}

/** -90 dBm maps to an empty bar and -40 dBm to a full one. */
export function signalPct(dbm: number | null): number | null {
  return dbm === null ? null : ((dbm + 90) / 50) * 100
}

export function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="row">
      <span className="k">{k}</span>
      <span className="v">{children}</span>
    </div>
  )
}

export function Gauge({
  label,
  value,
  pct,
  level,
}: {
  label: string
  value: string
  pct: number | null
  level?: string | null
}) {
  return (
    <div className="gauge">
      <div className="gauge-head">
        <span className="k">{label}</span>
        <span className="v">{value}</span>
      </div>
      <Meter pct={pct} level={level} />
    </div>
  )
}

export function NoData({ section, debug }: { section: SectionResult<unknown> | undefined; debug: boolean }) {
  return (
    <div>
      <p className="muted">Data is not available.</p>
      {debug && section?.error_detail && (
        <p className="debug">
          {section.error_type}: {section.error_detail}
        </p>
      )}
    </div>
  )
}
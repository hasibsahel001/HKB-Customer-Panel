export const NA = 'N/A'

export function show(value: unknown, suffix = ''): string {
  if (value === null || value === undefined || value === '') return NA
  return `${value}${suffix}`
}

export function formatBps(value: number | null | undefined): string {
  if (value === null || value === undefined) return NA
  const n = Math.abs(value)
  if (n < 1_000) return `${value} bps`
  if (n < 1_000_000) return `${(value / 1_000).toFixed(1)} Kbps`
  if (n < 1_000_000_000) return `${(value / 1_000_000).toFixed(2)} Mbps`
  return `${(value / 1_000_000_000).toFixed(2)} Gbps`
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return NA
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(2)} ${units[index]}`
}

export function parseTime(iso: string): Date {
  const hasZone = /(Z|[+-]\d{2}:\d{2})$/i.test(iso)
  return new Date(hasZone ? iso : `${iso}Z`)
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return NA
  const date = parseTime(iso)
  return Number.isNaN(date.getTime()) ? NA : date.toLocaleString()
}

export function ageSeconds(iso: string, nowMs: number): number {
  return Math.max(0, Math.round((nowMs - parseTime(iso).getTime()) / 1000))
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

const UNITS: Record<string, [string, string]> = {
  w: ['week', 'weeks'],
  d: ['day', 'days'],
  h: ['hour', 'hours'],
  m: ['minute', 'minutes'],
  s: ['second', 'seconds'],
}

/** RouterOS durations like "5w1d17h48m57s" become "5 weeks 1 day 17 hours". */
export function humanDuration(value: string | null | undefined): string {
  if (!value) return NA
  const matches = [...value.matchAll(/(\d+)([wdhms])/g)]
  if (matches.length === 0 || matches.map((m) => m[0]).join('') !== value) return value
  const parts = matches.map((m) => ({ n: Number(m[1]), unit: m[2] })).filter((p) => p.n > 0)
  if (parts.length === 0) return '0 seconds'
  return parts
    .slice(0, 3)
    .map((p) => `${p.n} ${UNITS[p.unit][p.n === 1 ? 0 : 1]}`)
    .join(' ')
}

/** RouterOS durations like "5w1d17h48m57s" become the short "5w 1d 17h". */
export function compactDuration(value: string | null | undefined): string {
  if (!value) return NA
  const matches = [...value.matchAll(/(\d+)([wdhms])/g)]
  if (matches.length === 0 || matches.map((m) => m[0]).join('') !== value) return value
  const parts = matches.map((m) => ({ n: Number(m[1]), unit: m[2] })).filter((p) => p.n > 0)
  if (parts.length === 0) return '0s'
  return parts
    .slice(0, 3)
    .map((p) => `${p.n}${p.unit}`)
    .join(' ')
}

/** "100Mbps" gives 100, "1Gbps" gives 1000. */
export function rateMbps(value: string | null | undefined): number | null {
  if (!value) return null
  const match = /^\s*(\d+(?:\.\d+)?)\s*([kmg]?)bps\s*$/i.exec(value)
  if (!match) return null
  const n = Number(match[1])
  const unit = match[2].toLowerCase()
  return unit === 'g' ? n * 1000 : unit === 'k' ? n / 1000 : n
}
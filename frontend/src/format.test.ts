import { describe, expect, it } from 'vitest'
import { ageSeconds, formatAge, formatBps, formatBytes, parseTime, show } from './format'

describe('show', () => {
  it('returns N/A for empty values', () => {
    expect(show(null)).toBe('N/A')
    expect(show(undefined)).toBe('N/A')
    expect(show('')).toBe('N/A')
  })
  it('keeps zero and appends a suffix', () => {
    expect(show(0, '%')).toBe('0%')
    expect(show(-55, ' dBm')).toBe('-55 dBm')
  })
})

describe('formatBps', () => {
  it('handles missing values', () => {
    expect(formatBps(null)).toBe('N/A')
    expect(formatBps(undefined)).toBe('N/A')
  })
  it('scales units', () => {
    expect(formatBps(0)).toBe('0 bps')
    expect(formatBps(999)).toBe('999 bps')
    expect(formatBps(1500)).toBe('1.5 Kbps')
    expect(formatBps(2005400)).toBe('2.01 Mbps')
    expect(formatBps(954624)).toBe('954.6 Kbps')
    expect(formatBps(1_500_000_000)).toBe('1.50 Gbps')
  })
})

describe('formatBytes', () => {
  it('scales units', () => {
    expect(formatBytes(null)).toBe('N/A')
    expect(formatBytes(1023)).toBe('1023 B')
    expect(formatBytes(1536)).toBe('1.50 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.00 MB')
  })
})

describe('time helpers', () => {
  it('treats timestamps without a zone as UTC', () => {
    expect(parseTime('2026-10-24T12:18:18').toISOString()).toBe('2026-10-24T12:18:18.000Z')
    expect(parseTime('2026-10-24T12:18:18Z').toISOString()).toBe('2026-10-24T12:18:18.000Z')
    expect(parseTime('2026-10-24T12:18:18+00:00').toISOString()).toBe('2026-10-24T12:18:18.000Z')
  })
  it('computes age', () => {
    const now = Date.UTC(2026, 9, 24, 12, 0, 30)
    expect(ageSeconds('2026-10-24T12:00:00Z', now)).toBe(30)
    expect(ageSeconds('2026-10-24T12:01:00Z', now)).toBe(0)
  })
  it('formats age', () => {
    expect(formatAge(5)).toBe('5s')
    expect(formatAge(75)).toBe('1m 15s')
    expect(formatAge(3700)).toBe('1h 1m')
  })
})
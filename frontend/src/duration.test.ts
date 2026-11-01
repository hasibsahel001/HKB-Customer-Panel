import { describe, expect, it } from 'vitest'
import { humanDuration, rateMbps } from './format'

describe('humanDuration', () => {
  it('shows at most three units with proper plurals', () => {
    expect(humanDuration('5w1d17h48m57s')).toBe('5 weeks 1 day 17 hours')
    expect(humanDuration('1w1d8h')).toBe('1 week 1 day 8 hours')
    expect(humanDuration('41m19s')).toBe('41 minutes 19 seconds')
    expect(humanDuration('1h27s')).toBe('1 hour 27 seconds')
    expect(humanDuration('45s')).toBe('45 seconds')
  })
  it('handles missing and unknown values', () => {
    expect(humanDuration(null)).toBe('N/A')
    expect(humanDuration('')).toBe('N/A')
    expect(humanDuration('12:30:00')).toBe('12:30:00')
    expect(humanDuration('0s')).toBe('0 seconds')
  })
})

describe('rateMbps', () => {
  it('converts units', () => {
    expect(rateMbps('100Mbps')).toBe(100)
    expect(rateMbps('1Gbps')).toBe(1000)
    expect(rateMbps('10Mbps')).toBe(10)
    expect(rateMbps('512kbps')).toBeCloseTo(0.512)
  })
  it('returns null for garbage', () => {
    expect(rateMbps(null)).toBeNull()
    expect(rateMbps('fast')).toBeNull()
  })
})
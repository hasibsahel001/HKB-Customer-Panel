import { describe, expect, it } from 'vitest'
import { mergeDiagnostics, overallOf } from './diagnosis'
import type { Diagnostics, Finding } from './types'

function finding(code: string, severity: string): Finding {
  return {
    code,
    title: code,
    severity,
    evidence: {},
    threshold: null,
    probable_causes: [],
    suggested_action: '',
    detected_at: 't',
  }
}

const base: Diagnostics = { overall: 'warning', count: 1, findings: [finding('b', 'warning')] }

describe('overallOf', () => {
  it('follows the same rules as the backend', () => {
    expect(overallOf([])).toBe('normal')
    expect(overallOf([finding('a', 'unknown')])).toBe('unknown')
    expect(overallOf([finding('a', 'unknown'), finding('b', 'warning')])).toBe('warning')
    expect(overallOf([finding('a', 'serious'), finding('b', 'critical')])).toBe('critical')
  })
  it('ignores informational findings', () => {
    expect(overallOf([finding('info', 'normal')])).toBe('normal')
    expect(overallOf([finding('info', 'normal'), finding('a', 'unknown')])).toBe('unknown')
  })
})

describe('mergeDiagnostics', () => {
  it('returns the base object when there is nothing to add', () => {
    expect(mergeDiagnostics(base, [])).toBe(base)
  })
  it('sorts by severity and recomputes the overall status', () => {
    const merged = mergeDiagnostics(base, [finding('a', 'serious')])
    expect(merged.findings.map((f) => f.code)).toEqual(['a', 'b'])
    expect(merged.overall).toBe('serious')
    expect(merged.count).toBe(2)
  })
  it('keeps informational findings last', () => {
    const merged = mergeDiagnostics(base, [finding('info', 'normal'), finding('u', 'unknown')])
    expect(merged.findings.map((f) => f.code)).toEqual(['b', 'u', 'info'])
    expect(merged.overall).toBe('warning')
  })
})
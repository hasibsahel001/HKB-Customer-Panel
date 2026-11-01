import type { Diagnostics, Finding } from './types'

const RANK: Record<string, number> = { critical: 0, serious: 1, warning: 2, unknown: 3, normal: 4 }

/** Findings with severity "normal" are facts worth showing; they never change the overall status. */
export function overallOf(findings: Finding[]): string {
  const levels = new Set(findings.map((f) => f.severity))
  for (const level of ['critical', 'serious', 'warning']) {
    if (levels.has(level)) return level
  }
  return [...levels].some((level) => level !== 'normal') ? 'unknown' : 'normal'
}

/** Adds the findings of the slow measurements to the main diagnostics. */
export function mergeDiagnostics(base: Diagnostics, extra: Finding[]): Diagnostics {
  if (extra.length === 0) return base
  const findings = [...base.findings, ...extra].sort(
    (a, b) => (RANK[a.severity] ?? 9) - (RANK[b.severity] ?? 9) || a.code.localeCompare(b.code),
  )
  return { ...base, findings, count: findings.length, overall: overallOf(findings) }
}
/** Helpers for the queue manager that do not need a browser, so they can be unit-tested. */

export const RATE_PRESETS = ['1M', '2M', '3M', '5M', '10M', '20M', '50M']

function toNumber(ip: string): number | null {
  const parts = ip.split('.')
  if (parts.length !== 4) return null
  let value = 0
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null
    const n = Number(part)
    if (n > 255) return null
    value = value * 256 + n
  }
  return value
}

/** True when `ip` is the target itself or lies inside a target such as 10.10.10.0/24. */
export function ipInTarget(ip: string, target: string): boolean {
  const [base, bits] = target.trim().split('/')
  if (bits === undefined) return base === ip
  const prefix = Number(bits)
  const a = toNumber(ip)
  const b = toNumber(base)
  if (a === null || b === null || !Number.isInteger(prefix) || prefix < 0 || prefix > 32) return false
  if (prefix === 0) return true
  const size = 2 ** (32 - prefix)
  return Math.floor(a / size) === Math.floor(b / size)
}

export function queueMatchesIp(targets: string[], ip: string): boolean {
  return targets.some((t) => ipInTarget(ip, t))
}

/** The name given to a queue created for one device. */
export function autoQueueName(ip: string): string {
  return `queue${ip}`
}

export function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size))
  return out
}
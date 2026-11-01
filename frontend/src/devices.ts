/** True when the MAC is locally administered, which phones use for "private" addresses. */
export function isPrivateMac(mac: string): boolean {
  const first = parseInt((mac.split(':')[0] ?? '').trim(), 16)
  return Number.isNaN(first) ? false : (first & 0x02) !== 0
}

export interface DeviceName {
  text: string
  named: boolean
}

export function deviceName(hostname: string | null, mac: string): DeviceName {
  if (hostname) return { text: hostname, named: true }
  if (isPrivateMac(mac)) return { text: 'IPhone', named: false }
  return { text: 'Unnamed device', named: false }
}
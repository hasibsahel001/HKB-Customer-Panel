import { api } from './api'
import type { DevicesData, Registration, WirelessAnalysis, WirelessData } from './types'

/** The customer's wireless link as read by the live (about every second) device request. */
export interface LiveWireless {
  interface: string | null
  registration_count: number
  registration: Registration | null
  analysis: WirelessAnalysis
}

export interface LiveDevicesData extends DevicesData {
  wireless?: LiveWireless | null
}

/**
 * The full check's wireless data with the live reading laid over it: signal, chains, CCQ, SNR and
 * the quality levels come from the live reading, the radio settings (SSID, frequency...) stay.
 */
export function mergeLiveWireless(
  base: WirelessData | null,
  live: LiveWireless | null | undefined,
): WirelessData | null {
  if (!live) return base
  if (!base) {
    return {
      interface: live.interface,
      running: null,
      disabled: null,
      ssid: null,
      frequency: null,
      band: null,
      channel_width: null,
      registration_count: live.registration_count,
      registration: live.registration,
      ccq_used: null,
      ccq_source: null,
      analysis: live.analysis,
    }
  }
  return {
    ...base,
    registration_count: live.registration_count,
    registration: live.registration,
    analysis: live.analysis,
  }
}

/** One fresh reading, used when a report picture is created. Null when it could not be read. */
export async function fetchLiveWireless(ip: string, tid: string): Promise<LiveWireless | null> {
  try {
    const data = await api<LiveDevicesData>('/api/customer/devices', { method: 'POST', body: { ip, tid } })
    return data.wireless ?? null
  } catch {
    return null
  }
}
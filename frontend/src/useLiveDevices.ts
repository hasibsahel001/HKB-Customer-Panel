import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { LiveDevicesData } from './liveWireless'

export interface LiveDevicesState {
  data: LiveDevicesData | null
  /** True while readings keep arriving; false after repeated failures. */
  ok: boolean
}

const INTERVAL_MS = 1000
const BACKOFF_MS = 4000
const GIVE_UP_AFTER = 3

/**
 * Re-reads the online devices of one customer about once a second.
 *
 * Requests never overlap (the next one is scheduled after the previous finished), polling pauses
 * while the tab is hidden or the page is not shown, and it stops when the customer changes.
 */
export function useLiveDevices(ip: string | null, tid: string | null, enabled: boolean): LiveDevicesState {
  const [state, setState] = useState<LiveDevicesState>({ data: null, ok: true })
  const key = ip && tid ? `${ip}|${tid}` : ''
  const lastKey = useRef('')

  useEffect(() => {
    if (lastKey.current !== key) {
      lastKey.current = key
      setState({ data: null, ok: true })
    }
    if (!key || !enabled) return

    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let failures = 0
    const controller = new AbortController()

    const schedule = (delay: number) => {
      if (!stopped) timer = setTimeout(tick, delay)
    }

    async function tick() {
      if (stopped) return
      if (document.hidden) {
        schedule(INTERVAL_MS)
        return
      }
      try {
        const data = await api<LiveDevicesData>('/api/customer/devices', {
          method: 'POST',
          body: { ip, tid },
          signal: controller.signal,
        })
        if (stopped) return
        failures = 0
        setState({ data, ok: true })
        schedule(INTERVAL_MS)
      } catch {
        if (stopped) return
        failures += 1
        if (failures >= GIVE_UP_AFTER) setState((old) => ({ ...old, ok: false }))
        schedule(BACKOFF_MS)
      }
    }

    schedule(INTERVAL_MS)
    return () => {
      stopped = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [key, enabled, ip, tid])

  return state
}
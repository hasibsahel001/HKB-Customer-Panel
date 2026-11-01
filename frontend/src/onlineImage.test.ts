import { describe, expect, it } from 'vitest'
import { deviceLimit } from './onlineImage'
import type { DeviceItem } from './types'

const base: DeviceItem = {
  ip: '192.168.0.5',
  mac_address: '00:08:22:A4:BA:DA',
  interface: 'bridge',
  hostname: null,
  lease_status: null,
  queue_scope: 'none',
  queue_names: [],
  queue_limit_upload_bps: null,
  queue_limit_download_bps: null,
  queue_ambiguous: false,
}

describe('deviceLimit', () => {
  it('says Free for a device without a queue', () => {
    expect(deviceLimit(base)).toEqual({ text: 'Free', kind: 'free' })
  })
  it('shows only the queue speed of a limited device', () => {
    const d = { ...base, queue_scope: 'own' as const, queue_names: ['q'], queue_limit_upload_bps: 2_000_000, queue_limit_download_bps: 4_000_000 }
    expect(deviceLimit(d).kind).toBe('limited')
    expect(deviceLimit(d).text).toContain('/')
  })
  it('does not guess when a shared queue is unclear', () => {
    const d = { ...base, queue_scope: 'shared' as const, queue_ambiguous: true }
    expect(deviceLimit(d).kind).toBe('free')
  })
  it('says Block for a 1 kbps queue, own or shared', () => {
    const own = { ...base, queue_scope: 'own' as const, queue_limit_upload_bps: 1000, queue_limit_download_bps: 1000 }
    expect(deviceLimit(own)).toEqual({ text: 'Block', kind: 'block' })
    const shared = { ...own, queue_scope: 'shared' as const }
    expect(deviceLimit(shared).kind).toBe('block')
  })
})
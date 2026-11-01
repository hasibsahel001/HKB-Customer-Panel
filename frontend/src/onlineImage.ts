import { deviceName } from './devices'
import { formatBps } from './format'
import { limitText } from './pages/shared'
import type { DeviceItem, DevicesData } from './types'
import { formatTakenAt } from './reportImage'

export interface OnlineDeviceRow {
  name: string
  ip: string
  limit: string
  kind: 'block' | 'limited' | 'free'
}

export interface OnlineImageModel {
  username: string
  download: string
  upload: string
  devices: OnlineDeviceRow[]
  moreCount: number
  count: number
  takenAt: string
}

const MAX_ROWS = 14

/** A queue of 1 kbps or less means the device is blocked. */
const BLOCK_BPS = 1000

/** What the picture says for one device: Block, its queue speed, or Free (no queue). */
export function deviceLimit(d: DeviceItem): { text: string; kind: 'block' | 'limited' | 'free' } {
  if (d.queue_scope === 'own' || (d.queue_scope === 'shared' && !d.queue_ambiguous)) {
    const up = d.queue_limit_upload_bps
    const down = d.queue_limit_download_bps
    const known = [up, down].filter((v): v is number => v !== null)
    if (known.length > 0) {
      if (Math.max(...known) <= BLOCK_BPS) return { text: 'Block', kind: 'block' }
      return { text: limitText(up, down), kind: 'limited' }
    }
  }
  return { text: 'Free', kind: 'free' }
}

export function buildOnlineModel(opts: { username: string | null; data: DevicesData; now: Date }): OnlineImageModel {
  const sorted = [...opts.data.devices].sort((a, b) => a.ip.localeCompare(b.ip, undefined, { numeric: true }))
  const shown = sorted.slice(0, MAX_ROWS)
  const traffic = opts.data.total_traffic
  return {
    username: opts.username ?? 'User not available',
    download: traffic?.download_bps != null ? formatBps(traffic.download_bps) : 'N/A',
    upload: traffic?.upload_bps != null ? formatBps(traffic.upload_bps) : 'N/A',
    devices: shown.map((d) => {
      const limit = deviceLimit(d)
      return { name: deviceName(d.hostname, d.mac_address).text, ip: d.ip, limit: limit.text, kind: limit.kind }
    }),
    moreCount: Math.max(0, sorted.length - shown.length),
    count: sorted.length,
    takenAt: formatTakenAt(opts.now),
  }
}

/* ---------------------------------------------------------------- drawing (browser only) */

const W = 900
const SCALE = 2
const PAD = 40
const SANS = '"Plus Jakarta Sans Variable", system-ui, "Segoe UI", Arial, sans-serif'
const MONO = '"JetBrains Mono Variable", Consolas, monospace'

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function card(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.save()
  ctx.shadowColor = 'rgba(37, 99, 235, 0.12)'
  ctx.shadowBlur = 18
  ctx.shadowOffsetY = 6
  ctx.fillStyle = '#ffffff'
  roundRect(ctx, x, y, w, h, 20)
  ctx.fill()
  ctx.restore()
  ctx.strokeStyle = '#dbe5fb'
  roundRect(ctx, x, y, w, h, 20)
  ctx.stroke()
}

function fit(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, weight: number, start: number, min: number, family: string) {
  let size = start
  ctx.font = `${weight} ${size}px ${family}`
  while (size > min && ctx.measureText(text).width > maxWidth) {
    size -= 2
    ctx.font = `${weight} ${size}px ${family}`
  }
  if (ctx.measureText(text).width <= maxWidth) return text
  let cut = text
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > maxWidth) cut = cut.slice(0, -1)
  return `${cut}…`
}

export async function renderOnlineImage(model: OnlineImageModel): Promise<Blob> {
  try {
    await Promise.all([document.fonts.load(`700 30px ${SANS}`), document.fonts.load(`500 20px ${MONO}`)])
  } catch {
    // system fonts are used instead
  }

  const HEAD = 96
  const usageY = HEAD + 22
  const usageH = 100
  const devY = usageY + usageH + 16
  const ROW = 42
  const rows = model.devices.length + (model.moreCount > 0 ? 1 : 0)
  const devH = 62 + Math.max(1, rows) * ROW + 10
  const height = devY + devH + 46

  const canvas = document.createElement('canvas')
  canvas.width = W * SCALE
  canvas.height = height * SCALE
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas is not available')
  ctx.scale(SCALE, SCALE)
  ctx.fillStyle = '#eef3ff'
  ctx.fillRect(0, 0, W, height)

  // header: product line and the username, kept small
  const gradient = ctx.createLinearGradient(0, 0, W, HEAD)
  gradient.addColorStop(0, '#1d4ed8')
  gradient.addColorStop(1, '#06b6d4')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, W, HEAD)
  ctx.textBaseline = 'alphabetic'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(255,255,255,0.85)'
  ctx.font = `700 15px ${SANS}`
  ctx.fillText('HKB CUSTOMER PANEL · REPORT', PAD, 34)
  ctx.fillStyle = '#ffffff'
  ctx.fillText(fit(ctx, model.username, W - PAD * 2, 800, 34, 22, SANS), PAD, 74)

  // download and upload
  const cardW = (W - PAD * 2 - 16) / 2
  const usage = [
    { x: PAD, label: 'DOWNLOAD', value: model.download, color: '#0891b2' },
    { x: PAD + cardW + 16, label: 'UPLOAD', value: model.upload, color: '#2563eb' },
  ]
  for (const item of usage) {
    card(ctx, item.x, usageY, cardW, usageH)
    ctx.fillStyle = '#64748b'
    ctx.font = `700 14px ${SANS}`
    ctx.fillText(item.label, item.x + 24, usageY + 34)
    ctx.fillStyle = item.color
    ctx.fillText(fit(ctx, item.value, cardW - 48, 800, 40, 22, SANS), item.x + 24, usageY + 78)
  }

  // devices
  card(ctx, PAD, devY, W - PAD * 2, devH)
  ctx.fillStyle = '#64748b'
  ctx.font = `700 14px ${SANS}`
  ctx.fillText('ONLINE DEVICES', PAD + 24, devY + 36)
  ctx.textAlign = 'right'
  ctx.fillStyle = '#2563eb'
  ctx.font = `800 18px ${SANS}`
  ctx.fillText(String(model.count), W - PAD - 24, devY + 36)
  ctx.textAlign = 'left'

  let y = devY + 62
  if (model.devices.length === 0) {
    ctx.fillStyle = '#64748b'
    ctx.font = `500 19px ${SANS}`
    ctx.fillText('No active devices', PAD + 24, y + 28)
  }
  for (const device of model.devices) {
    ctx.strokeStyle = '#e6ecfa'
    ctx.beginPath()
    ctx.moveTo(PAD + 24, y)
    ctx.lineTo(W - PAD - 24, y)
    ctx.stroke()
    ctx.fillStyle = '#0f172a'
    ctx.textAlign = 'left'
    ctx.fillText(fit(ctx, device.name, 280, 600, 19, 14, SANS), PAD + 24, y + 28)
    ctx.fillStyle = '#334155'
    ctx.font = `500 18px ${MONO}`
    ctx.fillText(device.ip, PAD + 24 + 300, y + 28)
    ctx.fillStyle = device.kind === 'block' ? '#dc2626' : device.kind === 'limited' ? '#b45309' : '#059669'
    ctx.textAlign = 'right'
    ctx.fillText(fit(ctx, device.limit, 210, 700, 18, 13, MONO), W - PAD - 24, y + 28)
    ctx.textAlign = 'left'
    y += ROW
  }
  if (model.moreCount > 0) {
    ctx.fillStyle = '#64748b'
    ctx.font = `500 17px ${SANS}`
    ctx.fillText(`+ ${model.moreCount} more device${model.moreCount === 1 ? '' : 's'}`, PAD + 24, y + 28)
  }

  ctx.fillStyle = '#64748b'
  ctx.font = `500 15px ${SANS}`
  ctx.fillText(`Checked ${model.takenAt}`, PAD, height - 16)

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The image could not be created'))), 'image/png')
  })
}
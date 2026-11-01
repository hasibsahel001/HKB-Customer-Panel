import type { UsageResult, UsageSample } from './actionTypes'
import { deviceName } from './devices'
import { formatBps } from './format'
import { formatTakenAt } from './reportImage'

export interface Peak {
  bps: number | null
  agoSeconds: number | null
}

export interface UsageSummary {
  windowSeconds: number
  up: Peak
  down: Peak
}

/** The highest sample of each direction and how many seconds before the last sample it happened. */
export function summarizeUsage(result: UsageResult): UsageSummary {
  const samples = result.samples
  const lastAt = samples.length > 0 ? samples[samples.length - 1].elapsed_ms : 0

  function peak(read: (sample: UsageSample) => number | null): Peak {
    let best: { value: number; at: number } | null = null
    for (const sample of samples) {
      const value = read(sample)
      if (value === null) continue
      if (best === null || value >= best.value) best = { value, at: sample.elapsed_ms }
    }
    if (best === null) return { bps: null, agoSeconds: null }
    return { bps: best.value, agoSeconds: Math.round((lastAt - best.at) / 1000) }
  }

  return {
    windowSeconds: result.seconds,
    up: peak((s) => s.up_bps),
    down: peak((s) => s.down_bps),
  }
}

export function agoText(seconds: number | null): string {
  if (seconds === null) return ''
  return seconds <= 0 ? 'just now' : `${seconds} s ago`
}

export type Unit = 'kbps' | 'mbps'
export type ImageMode = 'measured' | 'manual'

/** A speed shown in the image, with a short note under it (empty for typed values). */
export interface ImageSpeed {
  bps: number | null
  note: string
}

/** A believable speed near a whole number of Mbps: 3 gives something like 3.27. */
export function randomSpeedText(base: number, random: () => number = Math.random): string {
  const extra = Math.floor(random() * 90 + 5) / 100 // 0.05 to 0.94
  return String(Math.round((base + extra) * 100) / 100)
}

export function peakSpeed(peak: Peak, windowSeconds: number): ImageSpeed {
  if (peak.bps === null) return { bps: null, note: 'not measured' }
  const when = agoText(peak.agoSeconds)
  return { bps: peak.bps, note: `${when ? `${when} · ` : ''}last ${windowSeconds} s` }
}

/** A typed speed is used exactly as typed. An empty field means "not given". */
export function parseSpeed(text: string, unit: Unit): { ok: boolean; speed: ImageSpeed } {
  const cleaned = text.trim().replace(',', '.')
  if (cleaned === '') return { ok: true, speed: { bps: null, note: '' } }
  if (!/^\d+(\.\d+)?$/.test(cleaned)) return { ok: false, speed: { bps: null, note: '' } }
  const bps = Math.round(Number(cleaned) * (unit === 'mbps' ? 1_000_000 : 1_000))
  return { ok: true, speed: { bps, note: '' } }
}

export interface ImageDevice {
  name: string
  ip: string
}

export interface ImageModel {
  username: string
  takenAt: string
  mode: ImageMode
  labels: { up: string; down: string }
  up: { value: string; sub: string }
  down: { value: string; sub: string }
  deviceCount: number
  devices: ImageDevice[]
  moreCount: number
}

export interface ImageInput {
  username: string | null
  devices: { hostname: string | null; mac_address: string; ip: string }[]
  mode: ImageMode
  up: ImageSpeed
  down: ImageSpeed
  now: Date
}

export const MAX_DEVICES = 10

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function speedText(speed: ImageSpeed) {
  return speed.bps === null
    ? { value: 'N/A', sub: speed.note }
    : { value: formatBps(speed.bps), sub: speed.note }
}

export function buildImageModel(input: ImageInput): ImageModel {
  const shown = input.devices.slice(0, MAX_DEVICES)
  const { now } = input
  const measured = input.mode === 'measured'
  return {
    username: input.username ?? 'User not available',
    takenAt: formatTakenAt(now),
    mode: input.mode,
    labels: measured ? { up: 'PEAK UPLOAD', down: 'PEAK DOWNLOAD' } : { up: 'UPLOAD', down: 'DOWNLOAD' },
    up: speedText(input.up),
    down: speedText(input.down),
    deviceCount: input.devices.length,
    devices: shown.map((d) => ({ name: deviceName(d.hostname, d.mac_address).text, ip: d.ip })),
    moreCount: Math.max(0, input.devices.length - shown.length),
  }
}

export function imageFileName(username: string | null, now: Date): string {
  const safe = (username ?? 'customer').replace(/[^a-zA-Z0-9._-]+/g, '_').slice(0, 40) || 'customer'
  return `hkb-${safe}-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.png`
}

/* ---------------------------------------------------------------- drawing (browser only) */

const W = 1080
const SCALE = 2
const PAD = 48
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
  ctx.shadowColor = 'rgba(37, 99, 235, 0.14)'
  ctx.shadowBlur = 24
  ctx.shadowOffsetY = 8
  ctx.fillStyle = '#ffffff'
  roundRect(ctx, x, y, w, h, 24)
  ctx.fill()
  ctx.restore()
  ctx.strokeStyle = '#dbe5fb'
  ctx.lineWidth = 1
  roundRect(ctx, x, y, w, h, 24)
  ctx.stroke()
}

function fit(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  weight: number,
  start: number,
  min: number,
  family: string,
) {
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

async function loadFonts() {
  try {
    await Promise.all([
      document.fonts.load(`700 40px ${SANS}`),
      document.fonts.load(`500 20px ${SANS}`),
      document.fonts.load(`500 20px ${MONO}`),
    ])
  } catch {
    // The system fallback fonts are used when the web fonts are not available.
  }
}

export async function renderStatusImage(model: ImageModel): Promise<Blob> {
  await loadFonts()

  const usageY = 244
  const usageH = 170
  const devicesY = usageY + usageH + 24
  const rows = model.devices.length + (model.moreCount > 0 ? 1 : 0)
  const devicesH = 100 + Math.max(1, rows) * 46
  const height = devicesY + devicesH + 24 + 56

  const canvas = document.createElement('canvas')
  canvas.width = W * SCALE
  canvas.height = height * SCALE
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas is not available')
  ctx.scale(SCALE, SCALE)

  ctx.fillStyle = '#eef3ff'
  ctx.fillRect(0, 0, W, height)

  // header
  const gradient = ctx.createLinearGradient(0, 0, W, 220)
  gradient.addColorStop(0, '#1d4ed8')
  gradient.addColorStop(1, '#06b6d4')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, W, 220)
  ctx.textBaseline = 'alphabetic'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(255,255,255,0.85)'
  ctx.font = `700 20px ${SANS}`
  ctx.fillText('HKB CUSTOMER PANEL · REPORT', PAD, 58)
  ctx.fillStyle = 'rgba(255,255,255,0.75)'
  ctx.font = `700 16px ${SANS}`
  ctx.fillText('USERNAME', PAD, 106)
  ctx.fillStyle = '#ffffff'
  const nameText = fit(ctx, model.username, W - PAD * 2, 800, 64, 30, SANS)
  ctx.fillText(nameText, PAD, 172)

  // download and upload
  const cardW = (W - PAD * 2 - 24) / 2
  const usage = [
    { x: PAD, label: model.labels.down, data: model.down, color: '#0891b2' },
    { x: PAD + cardW + 24, label: model.labels.up, data: model.up, color: '#2563eb' },
  ]
  for (const item of usage) {
    card(ctx, item.x, usageY, cardW, usageH)
    ctx.fillStyle = '#64748b'
    ctx.font = `700 16px ${SANS}`
    ctx.fillText(item.label, item.x + 28, usageY + 44)
    ctx.fillStyle = item.color
    ctx.font = `800 54px ${SANS}`
    ctx.fillText(fit(ctx, item.data.value, cardW - 56, 800, 54, 30, SANS), item.x + 28, usageY + 108)
    if (item.data.sub) {
      ctx.fillStyle = '#64748b'
      ctx.font = `500 20px ${SANS}`
      ctx.fillText(item.data.sub, item.x + 28, usageY + 144)
    }
  }

  // devices
  card(ctx, PAD, devicesY, W - PAD * 2, devicesH)
  ctx.fillStyle = '#64748b'
  ctx.font = `700 16px ${SANS}`
  ctx.fillText('CONNECTED DEVICES', PAD + 28, devicesY + 44)
  const countText = String(model.deviceCount)
  ctx.font = `800 22px ${SANS}`
  const pillW = ctx.measureText(countText).width + 36
  ctx.fillStyle = '#e3edff'
  roundRect(ctx, W - PAD - 28 - pillW, devicesY + 18, pillW, 38, 19)
  ctx.fill()
  ctx.fillStyle = '#2563eb'
  ctx.textAlign = 'center'
  ctx.fillText(countText, W - PAD - 28 - pillW / 2, devicesY + 45)
  ctx.textAlign = 'left'

  let y = devicesY + 84
  if (model.devices.length === 0) {
    ctx.fillStyle = '#64748b'
    ctx.font = `500 22px ${SANS}`
    ctx.fillText('No active devices', PAD + 28, y + 30)
  }
  for (const device of model.devices) {
    ctx.strokeStyle = '#e6ecfa'
    ctx.beginPath()
    ctx.moveTo(PAD + 28, y)
    ctx.lineTo(W - PAD - 28, y)
    ctx.stroke()
    ctx.fillStyle = '#0f172a'
    ctx.textAlign = 'left'
    ctx.fillText(fit(ctx, device.name, 560, 600, 22, 16, SANS), PAD + 28, y + 31)
    ctx.fillStyle = '#334155'
    ctx.textAlign = 'right'
    ctx.font = `500 22px ${MONO}`
    ctx.fillText(device.ip, W - PAD - 28, y + 31)
    ctx.textAlign = 'left'
    y += 46
  }
  if (model.moreCount > 0) {
    ctx.fillStyle = '#64748b'
    ctx.font = `500 20px ${SANS}`
    ctx.fillText(`+ ${model.moreCount} more device${model.moreCount === 1 ? '' : 's'}`, PAD + 28, y + 30)
  }

  // footer
  ctx.fillStyle = '#64748b'
  ctx.font = `500 18px ${SANS}`
  ctx.fillText(`Checked ${model.takenAt}`, PAD, height - 24)

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The image could not be created'))), 'image/png')
  })
}

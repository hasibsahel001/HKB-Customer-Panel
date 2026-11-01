import { formatBps } from './format'

export interface ReportRow {
  label: string
  value: string
  color?: string
}

/** One block of a report picture: a big headline card and a list of rows under it. */
export interface ReportSection {
  title: string
  headline: { label: string; value: string; color: string }
  rows: ReportRow[]
}

export interface ReportModel {
  username: string
  sections: ReportSection[]
  takenAt: string
  /** A shorter, narrower picture for several blocks (the overall report). */
  compact: boolean
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

/** 2026-10-31 · 7:04 PM (12-hour clock) */
export function formatTakenAt(now: Date): string {
  const hours = now.getHours()
  const hour12 = hours % 12 === 0 ? 12 : hours % 12
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  return `${date} · ${hour12}:${pad(now.getMinutes())} ${hours >= 12 ? 'PM' : 'AM'}`
}

export function colorForLevel(level: string | null | undefined): string {
  switch (level) {
    case 'normal':
      return '#059669'
    case 'warning':
      return '#b45309'
    case 'serious':
      return '#c2410c'
    case 'critical':
      return '#dc2626'
    default:
      return '#64748b'
  }
}

export function buildFieldReportModel(opts: {
  username: string | null
  sections: ReportSection[]
  now: Date
  compact?: boolean
}): ReportModel {
  return {
    compact: opts.compact ?? false,
    username: opts.username ?? 'User not available',
    sections: opts.sections,
    takenAt: formatTakenAt(opts.now),
  }
}

export function imageFileNameFor(kind: string, username: string | null, now: Date): string {
  const safe = (username ?? 'customer').replace(/[^a-zA-Z0-9._-]+/g, '_').slice(0, 40) || 'customer'
  return `hkb-${kind}-${safe}-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.png`
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

const HEADLINE_H = 150
const GAP = 24

function sectionHeight(section: ReportSection): number {
  return HEADLINE_H + GAP + 70 + Math.max(1, section.rows.length) * 46
}

// compact (overall report): one small card per block
const C_W = 900
const C_HEAD = 138
const C_TOP = 28
const C_TITLE_H = 66
const C_ROW = 38

function compactHeight(section: ReportSection): number {
  return C_TITLE_H + Math.max(1, section.rows.length) * C_ROW + 14
}

function drawHeader(ctx: CanvasRenderingContext2D, width: number, headH: number, username: string, small: boolean) {
  const gradient = ctx.createLinearGradient(0, 0, width, headH)
  gradient.addColorStop(0, '#1d4ed8')
  gradient.addColorStop(1, '#06b6d4')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, width, headH)
  ctx.textBaseline = 'alphabetic'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(255,255,255,0.85)'
  ctx.font = `700 ${small ? 17 : 20}px ${SANS}`
  ctx.fillText('HKB CUSTOMER PANEL · REPORT', PAD, small ? 40 : 58)
  ctx.fillStyle = 'rgba(255,255,255,0.75)'
  ctx.font = `700 ${small ? 14 : 16}px ${SANS}`
  ctx.fillText('USERNAME', PAD, small ? 74 : 106)
  ctx.fillStyle = '#ffffff'
  const nameText = fit(ctx, username, width - PAD * 2, 800, small ? 44 : 64, 26, SANS)
  ctx.fillText(nameText, PAD, small ? 118 : 172)
}

function toBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The image could not be created'))), 'image/png')
  })
}

async function renderCompact(model: ReportModel): Promise<Blob> {
  const blocksH = model.sections.reduce((sum, section) => sum + compactHeight(section) + 16, 0)
  const height = C_HEAD + C_TOP + blocksH + 30

  const canvas = document.createElement('canvas')
  canvas.width = C_W * SCALE
  canvas.height = height * SCALE
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas is not available')
  ctx.scale(SCALE, SCALE)
  ctx.fillStyle = '#eef3ff'
  ctx.fillRect(0, 0, C_W, height)
  drawHeader(ctx, C_W, C_HEAD, model.username, true)

  let y = C_HEAD + C_TOP
  for (const section of model.sections) {
    const h = compactHeight(section)
    card(ctx, PAD, y, C_W - PAD * 2, h)
    // block title with its main value on the same line
    ctx.textAlign = 'left'
    ctx.fillStyle = '#64748b'
    ctx.font = `700 15px ${SANS}`
    ctx.fillText(section.headline.label.toUpperCase(), PAD + 26, y + 40)
    ctx.textAlign = 'right'
    ctx.fillStyle = section.headline.color
    ctx.font = `800 32px ${SANS}`
    ctx.fillText(fit(ctx, section.headline.value, 420, 800, 32, 18, SANS), C_W - PAD - 26, y + 44)
    ctx.textAlign = 'left'

    let rowY = y + C_TITLE_H + 24
    for (const row of section.rows) {
      ctx.strokeStyle = '#e6ecfa'
      ctx.beginPath()
      ctx.moveTo(PAD + 26, rowY - 26)
      ctx.lineTo(C_W - PAD - 26, rowY - 26)
      ctx.stroke()
      ctx.fillStyle = '#475569'
      ctx.textAlign = 'left'
      ctx.font = `600 19px ${SANS}`
      ctx.fillText(row.label, PAD + 26, rowY)
      ctx.fillStyle = row.color ?? '#0f172a'
      ctx.textAlign = 'right'
      ctx.font = `800 21px ${MONO}`
      ctx.fillText(fit(ctx, row.value, 340, 800, 21, 14, MONO), C_W - PAD - 26, rowY)
      ctx.textAlign = 'left'
      rowY += C_ROW
    }
    y += h + 16
  }

  ctx.fillStyle = '#64748b'
  ctx.textAlign = 'left'
  ctx.font = `500 16px ${SANS}`
  ctx.fillText(`Checked ${model.takenAt}`, PAD, height - 16)
  return toBlob(canvas)
}

export async function renderFieldReport(model: ReportModel): Promise<Blob> {
  await loadFonts()
  if (model.compact) return renderCompact(model)

  const top = 244
  const blocksH = model.sections.reduce((sum, section) => sum + sectionHeight(section) + GAP, 0)
  const height = top + blocksH + 36

  const canvas = document.createElement('canvas')
  canvas.width = W * SCALE
  canvas.height = height * SCALE
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas is not available')
  ctx.scale(SCALE, SCALE)

  ctx.fillStyle = '#eef3ff'
  ctx.fillRect(0, 0, W, height)
  drawHeader(ctx, W, 220, model.username, false)

  let blockY = top
  for (const section of model.sections) {
    // headline card
    card(ctx, PAD, blockY, W - PAD * 2, HEADLINE_H)
    ctx.fillStyle = '#64748b'
    ctx.font = `700 16px ${SANS}`
    ctx.fillText(section.headline.label.toUpperCase(), PAD + 28, blockY + 42)
    ctx.fillStyle = section.headline.color
    ctx.font = `800 54px ${SANS}`
    ctx.fillText(
      fit(ctx, section.headline.value, W - PAD * 2 - 56, 800, 54, 26, SANS),
      PAD + 28,
      blockY + 106,
    )

    // rows card
    const rowsY = blockY + HEADLINE_H + GAP
    const rowsH = 70 + Math.max(1, section.rows.length) * 46
    card(ctx, PAD, rowsY, W - PAD * 2, rowsH)
    let y = rowsY + 54
    for (const row of section.rows) {
      ctx.strokeStyle = '#e6ecfa'
      ctx.beginPath()
      ctx.moveTo(PAD + 28, y - 30)
      ctx.lineTo(W - PAD - 28, y - 30)
      ctx.stroke()
      ctx.fillStyle = '#475569'
      ctx.textAlign = 'left'
      ctx.font = `600 22px ${SANS}`
      ctx.fillText(row.label, PAD + 28, y)
      ctx.fillStyle = row.color ?? '#0f172a'
      ctx.textAlign = 'right'
      ctx.font = `800 24px ${MONO}`
      ctx.fillText(fit(ctx, row.value, 380, 800, 24, 16, MONO), W - PAD - 28, y)
      ctx.textAlign = 'left'
      y += 46
    }
    blockY = rowsY + rowsH + GAP
  }

  ctx.fillStyle = '#64748b'
  ctx.textAlign = 'left'
  ctx.font = `500 18px ${SANS}`
  ctx.fillText(`Checked ${model.takenAt}`, PAD, height - 22)
  return toBlob(canvas)
}

export { formatBps }
import { FormEvent, useRef, useState } from 'react'
import { ApiError, toApiError } from '../api'
import type { ActionCustomer } from '../actionTypes'
import type { Report } from '../types'
import { ErrorBox, Spinner } from '../ui'
import { ReportPreview } from './ReportPreview'
import { dataOf } from './shared'
import {
  buildImageModel,
  imageFileName,
  parseSpeed,
  randomSpeedText,
  renderStatusImage,
} from '../statusImage'
import type { Unit } from '../statusImage'

const PRESETS = [1, 2, 3, 4, 5, 6, 7]

function SpeedField({
  label,
  value,
  unit,
  onValue,
  onUnit,
}: {
  label: string
  value: string
  unit: Unit
  onValue: (value: string) => void
  onUnit: (unit: Unit) => void
}) {
  return (
    <div className="speed-field">
      <label className="field">
        {label}
        <span className="speed-input">
          <input
            value={value}
            onChange={(e) => onValue(e.target.value)}
            placeholder="5.68"
            inputMode="decimal"
            autoComplete="off"
          />
          <select value={unit} onChange={(e) => onUnit(e.target.value as Unit)} aria-label={`${label} unit`}>
            <option value="mbps">Mbps</option>
            <option value="kbps">Kbps</option>
          </select>
        </span>
      </label>
      <div className="qm-chips speed-presets" aria-label={`Random ${label.toLowerCase()} speed`}>
        {PRESETS.map((mbps) => (
          <button
            key={mbps}
            type="button"
            className="qm-chip"
            title={`A random speed a little above ${mbps} Mbps`}
            onClick={() => {
              onValue(randomSpeedText(mbps))
              onUnit('mbps')
            }}
          >
            ~{mbps}
          </button>
        ))}
      </div>
    </div>
  )
}

export function ImageView({ customer, report }: { customer: ActionCustomer; report: Report }) {
  const [downText, setDownText] = useState('')
  const [downUnit, setDownUnit] = useState<Unit>('mbps')
  const [upText, setUpText] = useState('')
  const [upUnit, setUpUnit] = useState<Unit>('mbps')
  const [phase, setPhase] = useState<'idle' | 'drawing' | 'ready'>('idle')
  const [error, setError] = useState<ApiError | null>(null)
  const [note, setNote] = useState('')
  const [blob, setBlob] = useState<Blob | null>(null)
  const takenAt = useRef(new Date())

  async function create(event?: FormEvent) {
    event?.preventDefault()
    setError(null)
    setNote('')

    const typedDown = parseSpeed(downText, downUnit)
    const typedUp = parseSpeed(upText, upUnit)
    if (!typedDown.ok || !typedUp.ok) {
      setNote('Enter numbers only, for example 5.68')
      return
    }
    const down = typedDown.speed
    const up = typedUp.speed

    setPhase('drawing')
    try {
      takenAt.current = new Date()
      const model = buildImageModel({
        username: customer.username,
        devices: dataOf(report.sections.devices)?.devices ?? [],
        mode: 'manual',
        up,
        down,
        now: takenAt.current,
      })
      setBlob(await renderStatusImage(model))
      setPhase('ready')
    } catch (e) {
      setError(toApiError(e))
      setPhase('idle')
    }
  }

  const working = phase === 'drawing'

  return (
    <>
      <form onSubmit={(e) => void create(e)}>
        <p className="muted small">
          Type the speeds, or press a number to get a random speed a little above it (for example ~3 gives 3.27).
          The numbers are shown in the image exactly as they appear here.
        </p>
        <div className="speed-grid">
          <SpeedField label="Download" value={downText} unit={downUnit} onValue={setDownText} onUnit={setDownUnit} />
          <SpeedField label="Upload" value={upText} unit={upUnit} onValue={setUpText} onUnit={setUpUnit} />
        </div>
        <div className="toolbar" style={{ marginTop: 12 }}>
          <button className="btn" type="submit" disabled={working}>
            {phase === 'ready' ? 'Create again' : 'Create image'}
          </button>
          {phase === 'drawing' && (
            <span className="muted">
              <Spinner /> Drawing the image…
            </span>
          )}
        </div>
      </form>

      <ErrorBox error={error} />
      {note && <div className="notice">{note}</div>}
      <ReportPreview blob={blob} alt="Customer status" fileName={imageFileName(customer.username, takenAt.current)} />
    </>
  )
}
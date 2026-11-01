import { ReactNode, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { ApiError, REASON_TEXT } from './api'

const LABEL: Record<string, string> = {
  normal: '✓ Normal',
  warning: '▲ Warning',
  serious: '◆ Serious',
  critical: '■ Critical',
  unknown: '? Unknown',
}

const KNOWN = ['normal', 'warning', 'serious', 'critical', 'unknown']

export function levelKey(level?: string | null): string {
  return level && KNOWN.includes(level) ? level : 'unknown'
}

export function Dot({ level }: { level?: string | null }) {
  return <span className={`dot dot-${levelKey(level)}`} aria-hidden="true" />
}

export function StatusBadge({ level }: { level?: string | null }) {
  const key = levelKey(level)
  return <span className={`badge badge-${key}`}>{LABEL[key]}</span>
}

export function Tri({ value }: { value: boolean | null | undefined }) {
  if (value === true) return <span className="badge badge-normal">✓ Yes</span>
  if (value === false) return <span className="badge badge-critical">■ No</span>
  return <span className="badge badge-unknown">? Unknown</span>
}

/** A horizontal gauge. A null value draws an empty bar. */
export function Meter({ pct, level }: { pct: number | null; level?: string | null }) {
  const width = pct === null ? 0 : Math.max(0, Math.min(100, pct))
  const tone = level ? `m-${levelKey(level)}` : 'm-accent'
  return (
    <div className="meter">
      <div className={`meter-fill ${tone}`} style={{ width: `${width}%` }} />
    </div>
  )
}

let openModals = 0

/**
 * A popup. It is drawn directly in <body> (a portal) so that animated or transformed parent cards
 * can never move it: inside such a card a "fixed" popup is positioned against the card, which made
 * the page jump down when a device row was clicked.
 * With strict=true it closes only with the Close button: clicking outside it or pressing Escape
 * does nothing, so work in progress is not lost by accident.
 */
export function Modal({
  title,
  onClose,
  strict = false,
  children,
}: {
  title: string
  onClose: () => void
  strict?: boolean
  children: ReactNode
}) {
  useEffect(() => {
    if (strict) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, strict])

  useEffect(() => {
    openModals += 1
    document.body.style.overflow = 'hidden'
    return () => {
      openModals -= 1
      if (openModals <= 0) {
        openModals = 0
        document.body.style.overflow = ''
      }
    }
  }, [])

  return createPortal(
    <div className="modal-back" onClick={strict ? undefined : onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn secondary" onClick={onClose} autoFocus>
            Close
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

export function Card({
  title,
  right,
  wide,
  children,
}: {
  title: string
  right?: ReactNode
  wide?: boolean
  children: ReactNode
}) {
  return (
    <section className={`card${wide ? ' wide' : ''}`}>
      <div className="card-head">
        <h2>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

export function KV({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([label, value]) => (
        <div key={label} className="kv-row">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />
}

export function ErrorBox({ error }: { error: ApiError | null }) {
  if (!error) return null
  return (
    <div className="error-box" role="alert">
      <div>{error.message}</div>
      {error.reasons.length > 0 && (
        <ul>
          {error.reasons.map((reason) => (
            <li key={reason}>{REASON_TEXT[reason] ?? reason}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
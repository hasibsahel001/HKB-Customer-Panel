import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import '../actions.css'
import { ApiError, api, toApiError } from '../api'
import { useAuth } from '../auth'
import type { ActionCustomer } from '../actionTypes'
import type { Report } from '../types'
import { ErrorBox } from '../ui'
import { ApAccessView } from './ApAccessView'
import { CableReportView } from './CableReportView'
import { CombinedReportView } from './CombinedReportView'
import { ImageView } from './ImageView'
import { QueueManager } from './QueueManager'
import { TroubleshootReportView } from './TroubleshootReportView'
import { UpdateView } from './UpdateView'

export type { ActionCustomer }

type View =
  | 'queues'
  | 'reboot'
  | 'update'
  | 'report-bandwidth'
  | 'report-troubleshoot'
  | 'report-cable'
  | 'report-combined'
  | 'ap-access'

function RebootView({ customer }: { customer: ActionCustomer }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function reboot() {
    setBusy(true)
    setError(null)
    try {
      await api('/api/router/reboot', {
        method: 'POST',
        body: { ip: customer.ip, tid: customer.tid, confirm: true },
      })
      setSent(true)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }

  if (sent) {
    return (
      <div className="ok-box">
        The reboot command was sent. The router will be unreachable for a minute or two; run a new check to see
        it come back.
      </div>
    )
  }

  return (
    <>
      <p>
        Reboot the router of <strong>{customer.username ?? customer.identity ?? customer.ip}</strong> ({customer.ip}
        )? The customer loses internet for about one to three minutes.
      </p>
      <ErrorBox error={error} />
      <div className="toolbar">
        {!armed && (
          <button className="btn secondary danger" onClick={() => setArmed(true)}>
            Reboot router
          </button>
        )}
        {armed && (
          <>
            <button className="btn" disabled={busy} onClick={() => void reboot()}>
              Yes, reboot now
            </button>
            <button className="btn secondary" disabled={busy} onClick={() => setArmed(false)}>
              Cancel
            </button>
          </>
        )}
      </div>
    </>
  )
}

interface NavItem {
  view: View
  label: string
  hint: string
}

const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Router',
    items: [
      { view: 'queues', label: 'Manage queues', hint: 'Speed limits' },
      { view: 'reboot', label: 'Reboot router', hint: 'Restart the router' },
      { view: 'update', label: 'Update RouterOS', hint: 'Latest stable + firmware' },
    ],
  },
  {
    title: 'Reports',
    items: [
      { view: 'report-bandwidth', label: 'Bandwidth report', hint: 'Devices and speeds' },
      { view: 'report-troubleshoot', label: 'Signal troubleshoot', hint: 'Signal, CCQ, SNR' },
      { view: 'report-cable', label: 'Cable report', hint: 'ether1 link status' },
      { view: 'report-combined', label: 'Signal + Cable', hint: 'Both in one picture' },
    ],
  },
  {
    title: 'Access',
    items: [{ view: 'ap-access', label: 'AP Access', hint: 'Via NAT or Local IP' }],
  },
]

const TITLES: Record<View, string> = {
  queues: 'Manage queues',
  reboot: 'Reboot router',
  update: 'Update RouterOS',
  'report-bandwidth': 'Bandwidth report',
  'report-troubleshoot': 'Signal troubleshoot report',
  'report-cable': 'Cable report',
  'report-combined': 'Signal + Cable report',
  'ap-access': 'AP Access',
}

/** The Manage panel: a sidebar that slides in from the right, with the options grouped by topic. */
export function ActionsModal({
  customer,
  report,
  onClose,
}: {
  customer: ActionCustomer
  report: Report
  onClose: () => void
}) {
  const { can } = useAuth()
  const [view, setView] = useState<View | null>(null)
  const canUpdate = can('router.update')

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (event: KeyboardEvent) => {
      // A popup opened from inside the panel handles Escape itself.
      if (event.key === 'Escape' && !document.querySelector('.modal-back')) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const name = customer.username ?? customer.identity ?? 'Customer'

  return createPortal(
    <div className="mg-back">
      <aside className="mg-drawer" role="dialog" aria-modal="true" aria-label="Manage">
        <header className="mg-head">
          <div className="mg-who">
            <strong>{name}</strong>
            <span className="muted mono small">
              {customer.ip} · TID {customer.tid}
            </span>
          </div>
          <button className="btn secondary" onClick={onClose} autoFocus>
            Close
          </button>
        </header>
        <div className="mg-body">
          <nav className="mg-nav" aria-label="Manage options">
            {GROUPS.map((group) => (
              <div key={group.title} className="mg-group">
                <div className="mg-group-title">{group.title}</div>
                {group.items.map((item) => {
                  const disabled = item.view === 'update' && !canUpdate
                  return (
                    <button
                      key={item.view}
                      className={`mg-item${view === item.view ? ' on' : ''}`}
                      disabled={disabled}
                      aria-current={view === item.view ? 'page' : undefined}
                      onClick={() => setView(item.view)}
                    >
                      <span className="mg-item-label">{item.label}</span>
                      <span className="mg-item-hint">{disabled ? 'Administrators only' : item.hint}</span>
                    </button>
                  )
                })}
              </div>
            ))}
          </nav>
          <section className="mg-content">
            {view === null && (
              <div className="mg-empty">
                <strong>Choose an option</strong>
                <span className="muted">Pick what you need from the list.</span>
              </div>
            )}
            {view !== null && <h3 className="mg-title">{TITLES[view]}</h3>}
            {view === 'queues' && <QueueManager ip={customer.ip} tid={customer.tid} />}
            {view === 'reboot' && <RebootView customer={customer} />}
            {view === 'update' && canUpdate && <UpdateView customer={customer} />}
            {view === 'report-bandwidth' && <ImageView customer={customer} report={report} />}
            {view === 'report-troubleshoot' && <TroubleshootReportView customer={customer} report={report} />}
            {view === 'report-cable' && <CableReportView customer={customer} report={report} />}
            {view === 'report-combined' && <CombinedReportView customer={customer} report={report} />}
            {view === 'ap-access' && <ApAccessView customer={customer} />}
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  )
}
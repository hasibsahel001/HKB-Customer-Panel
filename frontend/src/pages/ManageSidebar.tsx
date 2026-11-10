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
import { LimitUserView } from './LimitUserView'
import { QueueManager } from './QueueManager'
import { TroubleshootReportView } from './TroubleshootReportView'
import { UpdateView } from './UpdateView'

export type { ActionCustomer }

type View =
  | 'queues'
  | 'limit-user'
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
      { view: 'limit-user', label: 'Limit user', hint: 'Free the line for 2 min' },
      { view: 'reboot', label: 'Reboot router', hint: 'Restart the router' },
      { view: 'update', label: 'Update RouterOS', hint: 'Latest stable + firmware' },
    ],
  },
  {
    title: 'Reports',
    items: [
      { view: 'report-bandwidth', label: 'Bandwidth report', hint: 'Devices and speeds' },
      { view: 'report-troubleshoot', label: 'Signal report', hint: 'Signal, CCQ, SNR' },
      { view: 'report-cable', label: 'Cable report', hint: 'ether1 link status' },
      { view: 'report-combined', label: 'Overall report', hint: 'Signal, cable, ping' },
    ],
  },
  {
    title: 'Access',
    items: [{ view: 'ap-access', label: 'AP Access', hint: 'Via NAT or VPN' }],
  },
]

const TITLES: Record<View, string> = {
  queues: 'Manage queues',
  'limit-user': 'Limit user',
  reboot: 'Reboot router',
  update: 'Update RouterOS',
  'report-bandwidth': 'Bandwidth report',
  'report-troubleshoot': 'Signal report',
  'report-cable': 'Cable report',
  'report-combined': 'Overall report',
  'ap-access': 'AP Access',
}

/**
 * The Manage sidebar: always shown at the left of the customer page, with the options grouped in
 * folding sections. An option opens its page in a panel at the right; the sidebar stays usable.
 */
export function ManageSidebar({ customer, report }: { customer: ActionCustomer; report: Report }) {
  const { can } = useAuth()
  const canUpdate = can('router.update')
  const [view, setView] = useState<View | null>(null)
  // Always starts closed (narrow); the button opens it for as long as the customer page stays.
  const [collapsed, setCollapsed] = useState(true)
  const [closedGroups, setClosedGroups] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (view === null) return
    const onKey = (event: KeyboardEvent) => {
      // A popup opened from inside the panel handles Escape itself.
      if (event.key === 'Escape' && !document.querySelector('.modal-back')) setView(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [view])

  function toggleCollapsed() {
    setCollapsed(!collapsed)
  }

  return (
    <>
      <aside className={`side${collapsed ? ' collapsed' : ''}`} aria-label="Manage">
        <div className="side-top">
          {!collapsed && (
            <div className="side-who">
              <strong>Manage</strong>
            </div>
          )}
          <button
            className="side-toggle"
            onClick={toggleCollapsed}
            title={collapsed ? 'Open the sidebar' : 'Make the sidebar narrow'}
            aria-label={collapsed ? 'Open the sidebar' : 'Make the sidebar narrow'}
          >
            {collapsed ? '»' : '«'}
          </button>
        </div>
        <nav className="side-nav">
          {GROUPS.map((group) => {
            const open = collapsed || !closedGroups[group.title]
            return (
              <div key={group.title} className="side-group">
                {!collapsed && (
                  <button
                    className="side-group-head"
                    aria-expanded={open}
                    onClick={() => setClosedGroups({ ...closedGroups, [group.title]: open })}
                  >
                    <span>{group.title}</span>
                    <span className={`side-chevron${open ? ' open' : ''}`} aria-hidden="true">
                      ▾
                    </span>
                  </button>
                )}
                {collapsed && <div className="side-sep" aria-hidden="true" />}
                {open &&
                  group.items.map((item) => {
                    const disabled = item.view === 'update' && !canUpdate
                    return (
                      <button
                        key={item.view}
                        className={`side-item${view === item.view ? ' on' : ''}`}
                        disabled={disabled}
                        title={collapsed ? item.label : undefined}
                        aria-current={view === item.view ? 'page' : undefined}
                        onClick={() => setView(view === item.view ? null : item.view)}
                      >
                        <span className="side-badge" aria-hidden="true">
                          {item.label.slice(0, 1)}
                        </span>
                        {!collapsed && (
                          <span className="side-item-text">
                            <span className="side-item-label">{item.label}</span>
                            <span className="side-item-hint">{disabled ? 'Administrators only' : item.hint}</span>
                          </span>
                        )}
                      </button>
                    )
                  })}
              </div>
            )
          })}
        </nav>
      </aside>

      {view !== null &&
        createPortal(
          <section className="side-panel" role="dialog" aria-label={TITLES[view]}>
            <header className="side-panel-head">
              <h3>{TITLES[view]}</h3>
              <button className="btn secondary" onClick={() => setView(null)} autoFocus>
                Close
              </button>
            </header>
            <div className="side-panel-body">
              {view === 'queues' && <QueueManager ip={customer.ip} tid={customer.tid} />}
              {view === 'limit-user' && <LimitUserView customer={customer} />}
              {view === 'reboot' && <RebootView customer={customer} />}
              {view === 'update' && canUpdate && <UpdateView customer={customer} />}
              {view === 'report-bandwidth' && <ImageView customer={customer} report={report} />}
              {view === 'report-troubleshoot' && <TroubleshootReportView customer={customer} report={report} />}
              {view === 'report-cable' && <CableReportView customer={customer} report={report} />}
              {view === 'report-combined' && <CombinedReportView customer={customer} report={report} />}
              {view === 'ap-access' && <ApAccessView customer={customer} />}
            </div>
          </section>,
          document.body,
        )}
    </>
  )
}
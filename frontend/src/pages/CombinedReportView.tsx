import { useState } from 'react'
import { api } from '../api'
import { fetchLiveWireless } from '../liveWireless'
import { buildFieldReportModel, imageFileNameFor, renderFieldReport } from '../reportImage'
import type { ActionCustomer } from '../actionTypes'
import type { LiveResult, Report } from '../types'
import { ReportPreview } from './ReportPreview'
import { cableSection, pingSection, reportUsername, signalSection } from './reportSections'

/** Signal, cable and ping in one short picture, ready to copy. */
export function CombinedReportView({ customer, report }: { customer: ActionCustomer; report: Report }) {
  const [withSignal, setWithSignal] = useState(true)
  const [withCable, setWithCable] = useState(true)
  const [withPing, setWithPing] = useState(false)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [busy, setBusy] = useState(false)
  const [takenAt, setTakenAt] = useState(() => new Date())

  async function create() {
    setBusy(true)
    try {
      const [wireless, live] = await Promise.all([
        withSignal ? fetchLiveWireless(report.ip, report.technical_id) : Promise.resolve(null),
        withPing
          ? api<LiveResult>('/api/customer/live', { method: 'POST', body: { ip: report.ip, tid: report.technical_id } }).catch(
              () => null,
            )
          : Promise.resolve(null),
      ])
      const sections = []
      if (withSignal) sections.push(signalSection(report, wireless))
      if (withCable) sections.push(cableSection(report))
      if (withPing) sections.push(pingSection(live))
      const now = new Date()
      const model = buildFieldReportModel({ username: reportUsername(report), sections, now, compact: true })
      setTakenAt(now)
      setBlob(await renderFieldReport(model))
    } finally {
      setBusy(false)
    }
  }

  const none = !withSignal && !withCable && !withPing

  return (
    <>
      <p className="muted small">
        Tick what to include, create the picture, then press Copy image and paste it into the chat. Ping adds
        the quality of 8.8.8.8 and the packet loss, measured now on the customer's router.
      </p>
      <div className="report-ticks">
        <label className="toggle-row">
          <input type="checkbox" checked={withSignal} onChange={(e) => setWithSignal(e.target.checked)} />
          <span>Signal</span>
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={withCable} onChange={(e) => setWithCable(e.target.checked)} />
          <span>Cable</span>
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={withPing} onChange={(e) => setWithPing(e.target.checked)} />
          <span>Ping 8.8.8.8 + packet loss</span>
        </label>
      </div>
      <div className="toolbar">
        <button className="btn" disabled={busy || none} onClick={() => void create()}>
          {busy ? 'Creating…' : blob ? 'Create again' : 'Create report'}
        </button>
      </div>
      <ReportPreview blob={blob} alt="Overall report" fileName={imageFileNameFor('report', customer.username, takenAt)} />
    </>
  )
}
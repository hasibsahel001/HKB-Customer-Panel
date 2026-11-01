import { useState } from 'react'
import { fetchLiveWireless } from '../liveWireless'
import { buildFieldReportModel, imageFileNameFor, renderFieldReport } from '../reportImage'
import type { ActionCustomer } from '../actionTypes'
import type { Report } from '../types'
import { ReportPreview } from './ReportPreview'
import { reportUsername, signalSection } from './reportSections'

export function TroubleshootReportView({ customer, report }: { customer: ActionCustomer; report: Report }) {
  const [blob, setBlob] = useState<Blob | null>(null)
  const [busy, setBusy] = useState(false)
  const [takenAt, setTakenAt] = useState(() => new Date())

  async function create() {
    setBusy(true)
    try {
      const live = await fetchLiveWireless(report.ip, report.technical_id)
      const now = new Date()
      const model = buildFieldReportModel({
        username: reportUsername(report),
        sections: [signalSection(report, live)],
        now,
      })
      setTakenAt(now)
      setBlob(await renderFieldReport(model))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <p className="muted small">
        Remote radio, signal per chain, CCQ, SNR, noise floor and frequency in one picture, read right now
        from the router, for the field team to diagnose a signal problem.
      </p>
      <div className="toolbar">
        <button className="btn" disabled={busy} onClick={() => void create()}>
          {busy ? 'Creating…' : blob ? 'Create again' : 'Create report'}
        </button>
      </div>
      <ReportPreview blob={blob} alt="Signal report" fileName={imageFileNameFor('signal', customer.username, takenAt)} />
    </>
  )
}
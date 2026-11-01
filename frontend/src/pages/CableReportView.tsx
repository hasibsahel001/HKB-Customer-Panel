import { useState } from 'react'
import { buildFieldReportModel, imageFileNameFor, renderFieldReport } from '../reportImage'
import type { ActionCustomer } from '../actionTypes'
import type { Report } from '../types'
import { ReportPreview } from './ReportPreview'
import { cableSection, reportUsername } from './reportSections'

export function CableReportView({ customer, report }: { customer: ActionCustomer; report: Report }) {
  const [blob, setBlob] = useState<Blob | null>(null)
  const [busy, setBusy] = useState(false)
  const [takenAt, setTakenAt] = useState(() => new Date())

  async function create() {
    setBusy(true)
    try {
      const now = new Date()
      const model = buildFieldReportModel({
        username: reportUsername(report),
        sections: [cableSection(report)],
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
        Cable (ether1) link status, negotiated rate, duplex and link-down count, for a quick cable diagnosis
        without opening the dashboard.
      </p>
      <div className="toolbar">
        <button className="btn" disabled={busy} onClick={() => void create()}>
          {busy ? 'Creating…' : blob ? 'Create again' : 'Create report'}
        </button>
      </div>
      <ReportPreview blob={blob} alt="Cable report" fileName={imageFileNameFor('cable', customer.username, takenAt)} />
    </>
  )
}
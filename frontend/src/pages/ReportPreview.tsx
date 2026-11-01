import { useEffect, useState } from 'react'
import { canCopyImage, copyImage } from '../clipboard'

/** A finished report picture with its Copy and Save buttons. */
export function ReportPreview({ blob, alt, fileName }: { blob: Blob | null; alt: string; fileName: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setMessage('')
    if (!blob) {
      setUrl(null)
      return
    }
    const next = URL.createObjectURL(blob)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [blob])

  if (!blob || !url) return null

  function save() {
    if (!url) return
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    link.click()
  }

  async function copy() {
    if (!blob) return
    const ok = await copyImage(blob)
    setMessage(
      ok
        ? 'Image copied. Paste it into the chat.'
        : 'Copying a picture needs HTTPS or localhost in this browser. Use Save instead.',
    )
  }

  return (
    <div className="report-preview">
      <div className="toolbar">
        <button className="btn" onClick={() => void copy()} disabled={!canCopyImage()} title={canCopyImage() ? '' : 'Needs HTTPS or localhost'}>
          Copy image
        </button>
        <button className="btn secondary" onClick={save}>
          Save image
        </button>
        {message && <span className="muted small">{message}</span>}
        {!message && !canCopyImage() && (
          <span className="muted small">Copy needs HTTPS or localhost; use Save.</span>
        )}
      </div>
      <button type="button" className="img-save" onClick={save} title="Click to save the image">
        <img src={url} alt={alt} />
      </button>
    </div>
  )
}
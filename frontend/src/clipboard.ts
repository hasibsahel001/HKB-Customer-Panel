/** Copying to the clipboard. Browsers only allow it on HTTPS or localhost; text has a fallback. */

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fall through to the older way
  }
  try {
    const box = document.createElement('textarea')
    box.value = text
    box.setAttribute('readonly', '')
    box.style.position = 'fixed'
    box.style.opacity = '0'
    document.body.appendChild(box)
    box.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(box)
    return ok
  } catch {
    return false
  }
}

export function canCopyImage(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    typeof ClipboardItem !== 'undefined' &&
    !!navigator.clipboard &&
    typeof navigator.clipboard.write === 'function'
  )
}

export async function copyImage(blob: Blob): Promise<boolean> {
  if (!canCopyImage()) return false
  try {
    await navigator.clipboard.write([new ClipboardItem({ [blob.type || 'image/png']: blob })])
    return true
  } catch {
    return false
  }
}
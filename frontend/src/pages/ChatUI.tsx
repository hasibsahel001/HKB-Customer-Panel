import { useEffect, useRef, useState } from 'react'
import type { ClipboardEvent, KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import '../chat.css'
import { ApiError, toApiError } from '../api'
import { prepareImage, useChat } from '../chat'
import type { ChatMessage } from '../chat'
import { canCopyImage, copyImage, copyText } from '../clipboard'

const EMOJIS = [
  '😀', '😁', '😂', '🤣', '😊', '😍', '😘', '😎', '🤔', '😅', '😢', '😭',
  '😡', '🙏', '👍', '👎', '👏', '🙌', '💪', '🔥', '✅', '❌', '⚠️', '❤️',
  '🎉', '👋', '👌', '🤝', '📶', '🌐', '🔧', '⏳', '📞', '🏠', '🚀', '😴',
]

function clock(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

/** The button at the end of the search row; a red dot shows when messages are waiting. */
export function ChatButton() {
  const { unread, setOpen, online } = useChat()
  return (
    <button
      className="btn secondary chat-open"
      type="button"
      onClick={() => setOpen(true)}
      title={online.length > 0 ? `Online: ${online.join(', ')}` : 'Nobody else is online'}
    >
      <span aria-hidden="true">💬</span> Send message or picture
      {unread > 0 && (
        <span className="chat-badge" aria-label={`${unread} unread`}>
          {unread > 9 ? '9+' : unread}
        </span>
      )}
    </button>
  )
}

/** The popup in the top right corner: visible for 3 seconds, then gone (the red dot stays). */
export function ChatToast() {
  const { toast, setOpen, dismissToast } = useChat()
  if (!toast) return null
  return createPortal(
    <button
      className="chat-toast"
      onClick={() => {
        dismissToast()
        setOpen(true)
      }}
    >
      <strong>{toast.sender}</strong>
      <span>{toast.text ? toast.text.slice(0, 120) : '📷 Picture'}</span>
    </button>,
    document.body,
  )
}

function Bubble({ message, onReply }: { message: ChatMessage; onReply: (message: ChatMessage) => void }) {
  const [note, setNote] = useState('')
  const src = `/api/chat/image/${message.id}`

  function flash(text: string) {
    setNote(text)
    setTimeout(() => setNote(''), 1400)
  }

  async function copyMessage() {
    flash((await copyText(message.text)) ? 'Copied' : 'Could not copy')
  }

  async function copyPicture() {
    if (!canCopyImage()) {
      window.open(src, '_blank', 'noopener,noreferrer')
      return
    }
    try {
      const blob = await (await fetch(src, { credentials: 'same-origin' })).blob()
      flash((await copyImage(blob)) ? 'Picture copied' : 'Could not copy')
    } catch {
      flash('Could not copy')
    }
  }

  const status =
    message.mine && message.recipients
      ? message.read_by && message.read_by >= message.recipients
        ? '✓✓ Seen'
        : message.read_by
          ? `✓✓ Seen by ${message.read_by}/${message.recipients}`
          : '✓ Sent'
      : ''

  return (
    <div className={`chat-row ${message.mine ? 'mine' : 'theirs'}`}>
      <div className="chat-bubble">
        {!message.mine && <div className="chat-from">{message.sender}</div>}
        {message.has_image && (
          <img className="chat-img" src={src} alt="Sent picture" title="Click to copy the picture" onClick={() => void copyPicture()} />
        )}
        {message.text && (
          <div className="chat-text" title="Click to copy" onClick={() => void copyMessage()}>
            {message.text}
          </div>
        )}
        <div className="chat-meta">
          <span>{clock(message.created_at)}</span>
          {status && <span>{status}</span>}
          {note && <span className="chat-note">{note}</span>}
          {!message.mine && (
            <button className="chat-link" onClick={() => onReply(message)}>
              Reply
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/** The conversation and the box to write in. Sending is: type (or paste) and press Enter. */
export function ChatPanel() {
  const { open, setOpen, thread, online, send } = useChat()
  const [text, setText] = useState('')
  const [image, setImage] = useState<string | null>(null)
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null)
  const [emojiOpen, setEmojiOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [note, setNote] = useState('')
  const box = useRef<HTMLTextAreaElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const file = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) setTimeout(() => box.current?.focus(), 50)
  }, [open])

  useEffect(() => {
    const element = list.current
    if (element) element.scrollTop = element.scrollHeight
  }, [thread.length, open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape' && !document.querySelector('.modal-back, .side-panel')) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  if (!open) return null

  async function attach(blob: Blob) {
    setError(null)
    try {
      setImage(await prepareImage(blob))
    } catch (e) {
      setError(toApiError(e))
    }
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const item = Array.from(event.clipboardData.items).find((i) => i.kind === 'file' && i.type.startsWith('image/'))
    const blob = item?.getAsFile()
    if (blob) {
      event.preventDefault() // a pasted picture goes to the preview; pasted text and emojis paste normally
      void attach(blob)
    }
  }

  async function submit() {
    if (busy || (!text.trim() && !image)) return
    setBusy(true)
    setError(null)
    setNote('')
    try {
      const delivered = await send({ text, image, replyTo: replyTo?.id ?? null })
      if (delivered === 0) {
        setNote(replyTo ? 'That user is not available now.' : 'Nobody else is online, so nothing was sent.')
      } else {
        setText('')
        setImage(null)
        setReplyTo(null)
        setEmojiOpen(false)
      }
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
      box.current?.focus()
    }
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }

  function addEmoji(emoji: string) {
    const element = box.current
    const start = element?.selectionStart ?? text.length
    const end = element?.selectionEnd ?? text.length
    setText(text.slice(0, start) + emoji + text.slice(end))
    setTimeout(() => {
      element?.focus()
      element?.setSelectionRange(start + emoji.length, start + emoji.length)
    }, 0)
  }

  return createPortal(
    <section className="chat-panel" role="dialog" aria-label="Messages">
      <header className="chat-head">
        <div>
          <strong>Messages</strong>
          <div className="chat-online">
            <span className={`chat-dot${online.length > 0 ? ' on' : ''}`} />
            {online.length > 0 ? `Sent to everyone online: ${online.join(', ')}` : 'Nobody else is online'}
          </div>
        </div>
        <button className="btn secondary" onClick={() => setOpen(false)} aria-label="Close messages">
          ✕
        </button>
      </header>

      <div className="chat-list" ref={list}>
        {thread.length === 0 && <p className="muted chat-empty">No messages yet. Write one below; every online user gets it.</p>}
        {thread.map((message) => (
          <Bubble key={message.id} message={message} onReply={(m) => { setReplyTo(m); box.current?.focus() }} />
        ))}
      </div>

      <div className="chat-compose">
        {replyTo && (
          <div className="chat-reply">
            Replying to <strong>{replyTo.sender}</strong>: {replyTo.text ? replyTo.text.slice(0, 60) : 'picture'}
            <button className="chat-link" onClick={() => setReplyTo(null)}>
              ✕
            </button>
          </div>
        )}
        {image && (
          <div className="chat-preview">
            <img src={image} alt="Picture to send" />
            <button className="chat-link" onClick={() => setImage(null)}>
              Remove
            </button>
          </div>
        )}
        {error && <div className="chat-error">{error.message}</div>}
        {note && <div className="chat-note-line">{note}</div>}
        {emojiOpen && (
          <div className="chat-emojis">
            {EMOJIS.map((emoji) => (
              <button key={emoji} type="button" onClick={() => addEmoji(emoji)}>
                {emoji}
              </button>
            ))}
          </div>
        )}
        <div className="chat-inputrow">
          <button className="chat-tool" type="button" title="Emoji" onClick={() => setEmojiOpen(!emojiOpen)}>
            😊
          </button>
          <button className="chat-tool" type="button" title="Add a picture (or paste one with Ctrl+V)" onClick={() => file.current?.click()}>
            🖼️
          </button>
          <input
            ref={file}
            type="file"
            accept="image/*"
            hidden
            onChange={(event) => {
              const picked = event.target.files?.[0]
              if (picked) void attach(picked)
              event.target.value = ''
            }}
          />
          <textarea
            ref={box}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKey}
            onPaste={onPaste}
            rows={1}
            maxLength={2000}
            placeholder="Message… (Enter to send, Ctrl+V to paste a picture)"
          />
          <button className="btn chat-send" type="button" disabled={busy || (!text.trim() && !image)} onClick={() => void submit()}>
            {busy ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </section>,
    document.body,
  )
}
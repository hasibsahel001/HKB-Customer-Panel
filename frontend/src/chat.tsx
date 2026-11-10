import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'

export interface ChatMessage {
  id: number
  sender: string
  text: string
  has_image: boolean
  reply_to: number | null
  created_at: string
  mine?: boolean
  read?: boolean
  recipients?: number
  read_by?: number
}

interface PollResult {
  latest_id: number
  unread: number
  messages: ChatMessage[]
  online: string[]
}

interface ThreadResult {
  messages: ChatMessage[]
}

export interface ChatState {
  online: string[]
  unread: number
  thread: ChatMessage[]
  toast: ChatMessage | null
  open: boolean
  setOpen: (open: boolean) => void
  dismissToast: () => void
  send: (input: { text: string; image: string | null; replyTo: number | null }) => Promise<number>
}

const POLL_MS = 3000
const TOAST_MS = 3000

const ChatContext = createContext<ChatState | null>(null)

export function useChat(): ChatState {
  const value = useContext(ChatContext)
  if (!value) throw new Error('useChat needs the ChatProvider')
  return value
}

/** Every open panel polls the server; being seen polling is what makes a user "online". */
export function ChatProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState<string[]>([])
  const [unread, setUnread] = useState(0)
  const [thread, setThread] = useState<ChatMessage[]>([])
  const [toast, setToast] = useState<ChatMessage | null>(null)
  const [open, setOpen] = useState(false)
  const lastId = useRef<number | null>(null)
  const openRef = useRef(false)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    openRef.current = open
    if (open) setToast(null)
  }, [open])

  const loadThread = useCallback(async () => {
    try {
      const data = await api<ThreadResult>('/api/chat/thread')
      setThread(data.messages)
      const unreadIds = data.messages.filter((m) => !m.mine && !m.read).map((m) => m.id)
      if (unreadIds.length > 0 && openRef.current) {
        await api('/api/chat/read', { method: 'POST', body: { ids: unreadIds } })
        setUnread(0)
      }
    } catch {
      // the next poll tries again
    }
  }, [])

  useEffect(() => {
    let stopped = false

    async function tick() {
      try {
        const query = lastId.current === null ? '' : `?after=${lastId.current}`
        const data = await api<PollResult>(`/api/chat/poll${query}`)
        if (stopped) return
        setOnline(data.online)
        setUnread(data.unread)
        if (lastId.current === null) {
          lastId.current = data.latest_id // what was there before this page opened is not announced again
        } else if (data.messages.length > 0) {
          lastId.current = Math.max(lastId.current, ...data.messages.map((m) => m.id))
          if (!openRef.current) {
            setToast(data.messages[data.messages.length - 1])
            clearTimeout(toastTimer.current)
            toastTimer.current = setTimeout(() => setToast(null), TOAST_MS)
          }
        }
        if (openRef.current) await loadThread()
      } catch {
        // offline or logged out: the auth layer handles it, polling just keeps trying
      }
    }

    void tick()
    const timer = setInterval(() => void tick(), POLL_MS)
    return () => {
      stopped = true
      clearInterval(timer)
      clearTimeout(toastTimer.current)
    }
  }, [loadThread])

  useEffect(() => {
    if (open) void loadThread()
  }, [open, loadThread])

  const send = useCallback(
    async (input: { text: string; image: string | null; replyTo: number | null }) => {
      const result = await api<{ delivered: number }>('/api/chat/send', {
        method: 'POST',
        body: { text: input.text, image: input.image, reply_to: input.replyTo },
      })
      await loadThread()
      return result.delivered
    },
    [loadThread],
  )

  const value = useMemo<ChatState>(
    () => ({
      online,
      unread,
      thread,
      toast,
      open,
      setOpen,
      dismissToast: () => setToast(null),
      send,
    }),
    [online, unread, thread, toast, open, send],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

/** A picture from a file or the clipboard as a data URL, shrunk when it is large. */
export async function prepareImage(file: Blob): Promise<string> {
  const original = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('The picture could not be read'))
    reader.readAsDataURL(file)
  })
  const MAX_SIDE = 1600
  const LIMIT = 1_400_000
  if (file.size <= LIMIT && file.type !== 'image/bmp') {
    const probe = await loadImage(original).catch(() => null)
    if (probe && Math.max(probe.width, probe.height) <= MAX_SIDE) return original
  }
  const image = await loadImage(original)
  const scale = Math.min(1, MAX_SIDE / Math.max(image.width, image.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.width * scale))
  canvas.height = Math.max(1, Math.round(image.height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('The picture could not be prepared')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.85)
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('This file is not a picture'))
    image.src = src
  })
}
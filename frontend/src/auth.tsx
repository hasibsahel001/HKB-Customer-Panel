import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from './api'
import type { Me } from './types'

type Status = 'loading' | 'down' | 'setup' | 'anonymous' | 'authenticated'

interface AuthValue {
  status: Status
  me: Me | null
  can: (permission: string) => boolean
  login: (username: string, password: string) => Promise<void>
  setup: (username: string, password: string, confirm: string) => Promise<void>
  logout: () => Promise<void>
  updateMe: (me: Me) => void
  reload: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [me, setMe] = useState<Me | null>(null)

  const applyMe = useCallback((value: Me) => {
    setCsrfToken(value.csrf_token)
    setMe(value)
    setStatus('authenticated')
  }, [])

  const reload = useCallback(async () => {
    try {
      const state = await api<{ needs_setup: boolean }>('/api/setup/status')
      if (state.needs_setup) {
        setMe(null)
        setStatus('setup')
        return
      }
      applyMe(await api<Me>('/api/auth/me'))
    } catch (error) {
      setMe(null)
      setStatus(error instanceof ApiError && error.code === 'network' ? 'down' : 'anonymous')
    }
  }, [applyMe])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setCsrfToken('')
      setMe(null)
      setStatus((current) => (current === 'authenticated' ? 'anonymous' : current))
    })
    void reload()
    return () => setUnauthorizedHandler(null)
  }, [reload])

  useEffect(() => {
    const theme = me?.theme ?? 'system'
    const root = document.documentElement
    if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme)
    else root.removeAttribute('data-theme')
  }, [me?.theme])

  const login = useCallback(
    async (username: string, password: string) => {
      applyMe(await api<Me>('/api/auth/login', { method: 'POST', body: { username, password } }))
    },
    [applyMe],
  )

  const setup = useCallback(
    async (username: string, password: string, confirm: string) => {
      await api('/api/setup', {
        method: 'POST',
        body: { username, password, password_confirm: confirm },
      })
      await login(username, password)
    },
    [login],
  )

  const logout = useCallback(async () => {
    try {
      await api('/api/auth/logout', { method: 'POST' })
    } catch {
      // The local state is cleared either way.
    }
    setCsrfToken('')
    setMe(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo<AuthValue>(
    () => ({
      status,
      me,
      can: (permission: string) => me?.permissions.includes(permission) ?? false,
      login,
      setup,
      logout,
      updateMe: applyMe,
      reload,
    }),
    [status, me, login, setup, logout, applyMe, reload],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
import { FormEvent, useState } from 'react'
import { ApiError, toApiError } from '../api'
import { useAuth } from '../auth'
import { ErrorBox } from '../ui'

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-page">
      <section className="card">
        <h2>HKB Customer Panel</h2>
        <form className="stack" onSubmit={submit}>
          <label className="field">
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="field">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <ErrorBox error={error} />
          <button className="btn" type="submit" disabled={busy || !username || !password}>
            Sign in
          </button>
        </form>
      </section>
    </div>
  )
}
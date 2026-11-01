import { FormEvent, useState } from 'react'
import { ApiError, toApiError } from '../api'
import { useAuth } from '../auth'
import { ErrorBox } from '../ui'

export function SetupPage() {
  const { setup } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await setup(username, password, confirm)
    } catch (e) {
      setError(toApiError(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-page">
      <section className="card">
        <h2>HKB Customer Panel: first-time setup</h2>
        <p className="muted">Create the Super Admin account. This screen is shown only once.</p>
        <form className="stack" onSubmit={submit}>
          <label className="field">
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="field">
            Password (at least 10 characters)
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            Confirm password
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <ErrorBox error={error} />
          <button className="btn" type="submit" disabled={busy}>
            Create Super Admin
          </button>
        </form>
      </section>
    </div>
  )
}
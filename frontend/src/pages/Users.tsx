import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, ApiError, toApiError } from '../api'
import { useAuth } from '../auth'
import { formatTime } from '../format'
import type { UserItem } from '../types'
import { ErrorBox } from '../ui'

const ROLE_LABEL: Record<string, string> = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  support_agent: 'Support Agent',
  read_only: 'Read Only',
}

// UI hint only; the backend enforces these rules.
function assignable(actorRole: string): string[] {
  if (actorRole === 'super_admin') return ['super_admin', 'admin', 'support_agent', 'read_only']
  if (actorRole === 'admin') return ['support_agent', 'read_only']
  return []
}

function UserRowView({
  user,
  actorId,
  actorRole,
  onChanged,
  onError,
}: {
  user: UserItem
  actorId: number
  actorRole: string
  onChanged: () => void
  onError: (error: ApiError | null) => void
}) {
  const [resetting, setResetting] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const editable = user.id !== actorId && assignable(actorRole).includes(user.role)

  async function patch(body: { role?: string; is_active?: boolean }) {
    onError(null)
    try {
      await api(`/api/users/${user.id}`, { method: 'PATCH', body })
      onChanged()
    } catch (e) {
      onError(toApiError(e))
    }
  }

  async function reset() {
    onError(null)
    try {
      await api(`/api/users/${user.id}/password`, { method: 'POST', body: { new_password: password } })
      setResetting(false)
      setPassword('')
      onChanged()
    } catch (e) {
      onError(toApiError(e))
    }
  }

  async function remove() {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    onError(null)
    try {
      await api(`/api/users/${user.id}`, { method: 'DELETE' })
      onChanged()
    } catch (e) {
      onError(toApiError(e))
    } finally {
      setConfirmDelete(false)
    }
  }

  return (
    <tr>
      <td>{user.username}</td>
      <td>
        {editable ? (
          <select value={user.role} onChange={(e) => void patch({ role: e.target.value })}>
            {assignable(actorRole).map((role) => (
              <option key={role} value={role}>
                {ROLE_LABEL[role]}
              </option>
            ))}
          </select>
        ) : (
          ROLE_LABEL[user.role] ?? user.role
        )}
      </td>
      <td>{user.is_active ? 'Active' : 'Disabled'}</td>
      <td>{formatTime(user.created_at)}</td>
      <td>
        {editable && (
          <div className="toolbar">
            <button className="btn secondary" onClick={() => void patch({ is_active: !user.is_active })}>
              {user.is_active ? 'Disable' : 'Enable'}
            </button>
            {!resetting && (
              <button className="btn secondary" onClick={() => setResetting(true)}>
                Reset password
              </button>
            )}
            {resetting && (
              <>
                <input
                  type="password"
                  placeholder="New password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                />
                <button className="btn" onClick={() => void reset()} disabled={!password}>
                  Save
                </button>
                <button className="btn secondary" onClick={() => setResetting(false)}>
                  Cancel
                </button>
              </>
            )}
            <button className="btn secondary danger" onClick={() => void remove()}>
              {confirmDelete ? 'Confirm delete' : 'Delete'}
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

export function UsersPage() {
  const { me } = useAuth()
  const [users, setUsers] = useState<UserItem[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const roles = assignable(me?.role ?? '')
  const [role, setRole] = useState(roles[roles.length - 1] ?? 'read_only')

  const load = useCallback(async () => {
    try {
      setUsers(await api<UserItem[]>('/api/users'))
    } catch (e) {
      setError(toApiError(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function create(event: FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await api('/api/users', { method: 'POST', body: { username, password, role } })
      setUsername('')
      setPassword('')
      await load()
    } catch (e) {
      setError(toApiError(e))
    }
  }

  if (!me) return null

  return (
    <>
      <section className="card">
        <h2>Create user</h2>
        <form className="inline" onSubmit={create}>
          <label className="field">
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
          </label>
          <label className="field">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
          <button className="btn" type="submit" disabled={!username || !password}>
            Create
          </button>
        </form>
      </section>
      <ErrorBox error={error} />
      <section className="card" style={{ marginTop: 16 }}>
        <h2>Users</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <UserRowView
                  key={user.id}
                  user={user}
                  actorId={me.id}
                  actorRole={me.role}
                  onChanged={() => void load()}
                  onError={setError}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
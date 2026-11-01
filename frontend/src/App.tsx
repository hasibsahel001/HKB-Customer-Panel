import { useState } from 'react'
import { useAuth } from './auth'
import { AccountPage } from './pages/Account'
import { AuditPage } from './pages/Audit'
import { CheckPage } from './pages/Check'
import { LoginPage } from './pages/Login'
import { SetupPage } from './pages/Setup'
import { UsersPage } from './pages/Users'
import { Spinner } from './ui'

type Page = 'check' | 'users' | 'audit' | 'account'

export default function App() {
  const { status, me, can, logout, reload } = useAuth()
  const [page, setPage] = useState<Page>('check')

  if (status === 'loading') {
    return (
      <div className="center-page">
        <Spinner /> Loading
      </div>
    )
  }
  if (status === 'down') {
    return (
      <div className="center-page">
        <div className="error-box">Cannot reach the panel server. Is the backend running?</div>
        <button className="btn" onClick={() => void reload()}>
          Try again
        </button>
      </div>
    )
  }
  if (status === 'setup') return <SetupPage />
  if (status === 'anonymous' || !me) return <LoginPage />

  const tabs: { id: Page; label: string; visible: boolean }[] = [
    { id: 'check', label: 'Customer check', visible: can('customer.check') },
    { id: 'users', label: 'Users', visible: can('users.manage') },
    { id: 'audit', label: 'Audit log', visible: can('audit.view') },
    { id: 'account', label: 'Account', visible: true },
  ]

  return (
    <>
      <header className="topbar">
        <span className="brand">HKB Customer Panel</span>
        <nav className="nav">
          {tabs
            .filter((tab) => tab.visible)
            .map((tab) => (
              <button
                key={tab.id}
                className={page === tab.id ? 'active' : ''}
                onClick={() => setPage(tab.id)}
              >
                {tab.label}
              </button>
            ))}
        </nav>
        <div className="userbox">
          <span className="muted">
            {me.username} ({me.role})
          </span>
          <button className="btn secondary" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>
      <main className="page">
        {/* The check page stays mounted so its result survives tab switches. */}
        <div hidden={page !== 'check'}>
          <CheckPage active={page === 'check'} />
        </div>
        {page === 'users' && can('users.manage') && <UsersPage />}
        {page === 'audit' && can('audit.view') && <AuditPage />}
        {page === 'account' && <AccountPage />}
      </main>
    </>
  )
}
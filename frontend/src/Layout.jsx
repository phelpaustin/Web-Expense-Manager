import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Dashboard', icon: '📊', end: true },
  { to: '/expenses', label: 'Expenses', icon: '🧾' },
  { to: '/income', label: 'Income', icon: '💵' },
  { to: '/recurring', label: 'Recurring', icon: '🔁' },
  { to: '/bills', label: 'Bills', icon: '📒' },
  { to: '/trips', label: 'Trips', icon: '🧳' },
  { to: '/groups', label: 'Groups', icon: '👨‍👩‍👧' },
  { to: '/prices', label: 'Prices', icon: '📈' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

const SEVERITY_ICON = { critical: '🔴', warning: '🟠', caution: '🟡', info: '💡' }

function NotificationBell({ alerts }) {
  const [open, setOpen] = useState(false)
  const count = alerts.length
  const topSeverity = alerts.reduce((worst, a) => {
    const order = { critical: 3, warning: 2, caution: 1, info: 0 }
    return order[a.severity] > (order[worst] ?? -1) ? a.severity : worst
  }, null)

  return (
    <div className="notif-bell-wrap">
      <button className="notif-bell" onClick={() => setOpen((v) => !v)} title="Budget alerts">
        🔔
        {count > 0 && <span className={`notif-badge notif-${topSeverity}`}>{count}</span>}
      </button>
      {open && (
        <>
          <div className="notif-backdrop" onClick={() => setOpen(false)} />
          <div className="notif-dropdown">
            <h3>Budget alerts</h3>
            {count === 0 ? (
              <p className="subtitle">No alerts — you're within budget.</p>
            ) : (
              <ul className="notif-list">
                {alerts.map((a) => (
                  <li key={a.id} className={`notif-item notif-${a.severity}`}>
                    <span className="notif-icon">{SEVERITY_ICON[a.severity]}</span>
                    <span>{a.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default function Layout({ user, onLogout, error, loading, alerts = [] }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">💳 Expenses</div>
        <nav className="nav">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              <span className="nav-icon">{l.icon}</span>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-email" title={user.email}>
            {user.name || user.email}
          </div>
          <button className="logout-btn" onClick={onLogout}>
            Log out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <div className="topbar">
          <NotificationBell alerts={alerts} />
        </div>
        {loading && <p>Loading…</p>}
        {error && (
          <div className="error">
            <strong>Something went wrong.</strong>
            <p>{error}</p>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}


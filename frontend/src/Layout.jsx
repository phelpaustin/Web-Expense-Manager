import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Dashboard', icon: '📊', end: true },
  { to: '/expenses', label: 'Expenses', icon: '🧾' },
  { to: '/income', label: 'Income', icon: '💵' },
  { to: '/recurring', label: 'Recurring', icon: '🔁' },
  { to: '/bills', label: 'Bills', icon: '📒' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function Layout({ user, onLogout, error, loading }) {
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
            {user.email}
          </div>
          <button className="logout-btn" onClick={onLogout}>
            Log out
          </button>
        </div>
      </aside>

      <main className="main-content">
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

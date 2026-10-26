import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

// Phones get a bottom bar instead of the sidebar: the places you use most, a big Add button in the
// middle, and a More sheet for the rest (which is also where Log out lives).
export const PHONE_QUERY = '(max-width: 760px)'

const MORE_LINKS = [
  { to: '/income', label: 'Income', icon: '💵' },
  { to: '/recurring', label: 'Recurring', icon: '🔁' },
  { to: '/import', label: 'Import', icon: '📥' },
  { to: '/trips', label: 'Trips', icon: '🧳' },
  { to: '/settings', label: 'Settings', icon: '⚙️', badge: 'invitations' },
]

function Sheet({ label, onClose, returnTo, children }) {
  const ref = useRef(null)
  useEffect(() => {
    ref.current?.querySelector('a, button')?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      returnTo.current?.focus() // Safari does not focus a button when it is clicked, so go back to it by name
    }
  }, [onClose, returnTo])
  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={label} ref={ref}>
      <div className="sheet-grip" aria-hidden="true" />
      <div className="sheet-title">{label}</div>
      {children}
      <button type="button" className="sheet-cancel" onClick={onClose}>
        Cancel
      </button>
    </div>
  )
}

export default function MobileNav({ user, onLogout, invitationCount = 0, onUploadReceipt }) {
  const [sheet, setSheet] = useState(null) // null | 'add' | 'more'
  const location = useLocation()
  const navigate = useNavigate()
  const fileInput = useRef(null)
  const addButton = useRef(null)
  const moreButton = useRef(null)
  const close = () => setSheet(null)
  const closeRef = useRef(close)
  closeRef.current = close
  const stableClose = useRef(() => closeRef.current()).current

  // Going anywhere closes whatever sheet is open.
  useEffect(() => {
    setSheet(null)
  }, [location.pathname, location.search])

  const inMore = MORE_LINKS.some((l) => location.pathname === l.to || location.pathname.startsWith(`${l.to}/`))
  const go = (to) => () => {
    setSheet(null)
    navigate(to)
  }

  async function receiptChosen(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setSheet(null)
    navigate('/spending?view=receipts')
    await onUploadReceipt?.(file)
  }

  const link = (to, label, icon, end) => (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? 'bottom-link active' : 'bottom-link')}>
      <span className="bottom-icon" aria-hidden="true">{icon}</span>
      {label}
    </NavLink>
  )

  return (
    <>
      {sheet && <div className="sheet-backdrop" onClick={close} />}

      {sheet === 'add' && (
        <Sheet label="Add" onClose={stableClose} returnTo={addButton}>
          <button type="button" className="sheet-item" onClick={go('/spending?view=items')}>
            <strong>Add expense</strong>
            <span>One purchase, quickly</span>
          </button>
          <button type="button" className="sheet-item" onClick={go('/spending?view=items&add=bill')}>
            <strong>Add a bill with items</strong>
            <span>A shop trip with its lines</span>
          </button>
          <button type="button" className="sheet-item sheet-item-main" onClick={() => fileInput.current?.click()}>
            <strong>Upload a receipt</strong>
            <span>A photo or PDF, itemise later</span>
          </button>
        </Sheet>
      )}

      {sheet === 'more' && (
        <Sheet label="More" onClose={stableClose} returnTo={moreButton}>
          {MORE_LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} className="sheet-item sheet-link">
              <span><span aria-hidden="true">{l.icon}</span> <strong>{l.label}</strong></span>
              {l.badge === 'invitations' && invitationCount > 0 && (
                <span className="nav-badge" role="status" aria-label={`${invitationCount} invitation${invitationCount === 1 ? '' : 's'} waiting`}>
                  {invitationCount}
                </span>
              )}
            </NavLink>
          ))}
          <div className="sheet-user">
            <span className="sheet-user-name" title={user.email}>{user.name || user.email}</span>
            <button type="button" className="logout-btn" onClick={onLogout}>
              Log out
            </button>
          </div>
        </Sheet>
      )}

      <nav className="bottom-bar" aria-label="Main">
        {link('/', 'Dashboard', '📊', true)}
        {link('/spending', 'Spending', '🧾')}
        <div className="bottom-add-slot">
          <button
            ref={addButton}
            type="button"
            className={sheet === 'add' ? 'bottom-add open' : 'bottom-add'}
            aria-label={sheet === 'add' ? 'Close add menu' : 'Add'}
            aria-haspopup="dialog"
            aria-expanded={sheet === 'add'}
            onClick={() => setSheet(sheet === 'add' ? null : 'add')}
          >
            {sheet === 'add' ? '✕' : '＋'}
          </button>
        </div>
        {link('/insights', 'Insights', '📈')}
        <button
          ref={moreButton}
          type="button"
          className={sheet === 'more' || inMore ? 'bottom-link active' : 'bottom-link'}
          aria-haspopup="dialog"
          aria-expanded={sheet === 'more'}
          onClick={() => setSheet(sheet === 'more' ? null : 'more')}
        >
          <span className="bottom-icon" aria-hidden="true">☰</span>
          More
          {invitationCount > 0 && <span className="bottom-dot" aria-hidden="true" />}
        </button>
      </nav>

      <input ref={fileInput} type="file" aria-label="Receipt file" accept="application/pdf,image/*" onChange={receiptChosen} hidden />
    </>
  )
}

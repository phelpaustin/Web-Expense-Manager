import { useState } from 'react'
import {
  changePassword,
  addCategory,
  deleteCategory,
  addSubcategory,
  deleteSubcategory,
  addUnit,
  deleteUnit,
  addShop,
  deleteShop,
  setBaseCurrency,
} from '../api/client.js'
import { setDisplayCurrency } from '../format.js'

function ChipList({ items, onDelete }) {
  if (!items || items.length === 0) return <p className="muted-note">None yet.</p>
  return (
    <div className="chips">
      {items.map((it) => (
        <span key={it} className="chip">
          {it}
          <button className="chip-x" onClick={() => onDelete(it)} title="Remove">
            ✕
          </button>
        </span>
      ))}
    </div>
  )
}

function AddInline({ placeholder, onAdd }) {
  const [value, setValue] = useState('')
  return (
    <form
      className="inline-add"
      onSubmit={(e) => {
        e.preventDefault()
        const v = value.trim()
        if (v) {
          onAdd(v)
          setValue('')
        }
      }}
    >
      <input type="text" placeholder={placeholder} value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="submit">Add</button>
    </form>
  )
}

export default function SettingsPage({ user, options, onOptionsUpdated, onError, onDeleteAccount }) {
  const [tab, setTab] = useState('account')

  // Account tab
  const [pwCurrent, setPwCurrent] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [pwMsg, setPwMsg] = useState(null)
  const [pwBusy, setPwBusy] = useState(false)

  // Delete account
  const [delPassword, setDelPassword] = useState('')
  const [delBusy, setDelBusy] = useState(false)
  const [delError, setDelError] = useState(null)

  // App-data tab
  const [selectedCat, setSelectedCat] = useState('')

  async function apply(promise) {
    try {
      const updated = await promise
      onOptionsUpdated(updated)
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault()
    setPwMsg(null)
    if (pwNew !== pwConfirm) {
      setPwMsg({ type: 'error', text: 'New passwords do not match.' })
      return
    }
    setPwBusy(true)
    try {
      await changePassword(pwCurrent, pwNew)
      setPwMsg({ type: 'ok', text: 'Password changed successfully.' })
      setPwCurrent('')
      setPwNew('')
      setPwConfirm('')
    } catch (err) {
      setPwMsg({ type: 'error', text: err.message })
    } finally {
      setPwBusy(false)
    }
  }

  const subcats = (options.subcategories && options.subcategories[selectedCat]) || []

  async function handleDelete(e) {
    e.preventDefault()
    setDelError(null)
    if (!window.confirm('This permanently deletes your account and all data. Continue?')) return
    setDelBusy(true)
    try {
      await onDeleteAccount(delPassword)
    } catch (err) {
      setDelError(err.message)
      setDelBusy(false)
    }
  }

  return (
    <>
      <h1 className="page-title">⚙️ Settings</h1>

      <div className="tabs">
        <button className={tab === 'account' ? 'tab active' : 'tab'} onClick={() => setTab('account')}>
          Account
        </button>
        <button className={tab === 'data' ? 'tab active' : 'tab'} onClick={() => setTab('data')}>
          App data
        </button>
      </div>

      {tab === 'account' && (
        <section className="panel">
          <h2>Account</h2>
          <p className="muted-note">Signed in as <strong>{user.email}</strong></p>

          <h3>Change password</h3>
          <form className="stack-form" onSubmit={handleChangePassword}>
            <input
              type="password"
              placeholder="Current password"
              required
              value={pwCurrent}
              onChange={(e) => setPwCurrent(e.target.value)}
            />
            <input
              type="password"
              placeholder="New password (min 6 characters)"
              required
              minLength={6}
              value={pwNew}
              onChange={(e) => setPwNew(e.target.value)}
            />
            <input
              type="password"
              placeholder="Confirm new password"
              required
              value={pwConfirm}
              onChange={(e) => setPwConfirm(e.target.value)}
            />
            {pwMsg && <div className={pwMsg.type === 'ok' ? 'ok-note' : 'auth-error'}>{pwMsg.text}</div>}
            <button type="submit" disabled={pwBusy}>
              {pwBusy ? 'Saving…' : 'Change password'}
            </button>
          </form>
        </section>
      )}

      {tab === 'account' && (
        <section className="panel danger-zone">
          <h2>Danger zone</h2>
          <p className="muted-note">
            Permanently delete your account and all expenses, income, budgets, and settings. This
            cannot be undone.
          </p>
          <form className="add-form" onSubmit={handleDelete}>
            <input
              type="password"
              placeholder="Confirm your password"
              required
              value={delPassword}
              onChange={(e) => setDelPassword(e.target.value)}
            />
            <button type="submit" className="danger-btn" disabled={delBusy}>
              {delBusy ? 'Deleting…' : 'Delete my account'}
            </button>
          </form>
          {delError && <div className="auth-error" style={{ marginTop: '0.6rem' }}>{delError}</div>}
        </section>
      )}

      {tab === 'data' && (
        <>
          <section className="panel">
            <h2>Display currency</h2>
            <p className="muted-note">How amounts are shown across the app.</p>
            <select
              className="cat-select"
              value={options.base_currency || 'SEK'}
              onChange={async (e) => {
                const updated = await setBaseCurrency(e.target.value).catch((err) => {
                  onError(err.message)
                  return null
                })
                if (updated) {
                  setDisplayCurrency(updated.base_currency)
                  onOptionsUpdated(updated)
                }
              }}
            >
              {['SEK', 'USD', 'EUR', 'GBP', 'INR', 'DKK', 'NOK'].map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </section>

          <section className="panel">
            <h2>Categories</h2>
            <ChipList items={options.categories} onDelete={(name) => apply(deleteCategory(name))} />
            <AddInline placeholder="New category" onAdd={(name) => apply(addCategory(name))} />
          </section>

          <section className="panel">
            <h2>Subcategories</h2>
            <select
              className="cat-select"
              value={selectedCat}
              onChange={(e) => setSelectedCat(e.target.value)}
            >
              <option value="">Select a category…</option>
              {options.categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            {selectedCat && (
              <>
                <ChipList
                  items={subcats}
                  onDelete={(name) => apply(deleteSubcategory(selectedCat, name))}
                />
                <AddInline
                  placeholder={`New subcategory for ${selectedCat}`}
                  onAdd={(name) => apply(addSubcategory(selectedCat, name))}
                />
              </>
            )}
          </section>

          <section className="panel">
            <h2>Units</h2>
            <ChipList items={options.units} onDelete={(name) => apply(deleteUnit(name))} />
            <AddInline placeholder="New unit" onAdd={(name) => apply(addUnit(name))} />
          </section>

          <section className="panel">
            <h2>Shops</h2>
            <ChipList items={options.shops} onDelete={(name) => apply(deleteShop(name))} />
            <AddInline placeholder="New shop" onAdd={(name) => apply(addShop(name))} />
          </section>
        </>
      )}
    </>
  )
}

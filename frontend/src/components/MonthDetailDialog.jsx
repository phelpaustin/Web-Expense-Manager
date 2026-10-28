import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { fetchExpenses, fetchIncome, updateExpense, deleteExpense, bulkUpdateExpenses, bulkCopyExpenses } from '../api/client.js'
import { money } from '../format.js'
import CurrencySelect from './CurrencySelect.jsx'
import { groupIntoBills, billTotal, categorySummary } from '../billGroups.js'
import './monthDetail.css'
import {
  monthRange, shiftMonth, monthTitle, currentMonthKey, incomeInMonth, totalsByCurrency, includesIncome, scopeFilters,
  editFormFor, expenseChanges, canEditExpense, tripCategoryIds, movableTrips, spaceName, moveChanges, movedMessage, copiedMessage,
} from '../monthDetail.js'

const PAGE_SIZE = 200
const MAX_PAGES = 10

async function loadMonthExpenses(month, scope, spaceIds) {
  const { from, to } = monthRange(month)
  const items = []
  let total = 0
  for (let page = 1; page <= MAX_PAGES; page++) {
    const res = await fetchExpenses({ ...scopeFilters(scope, spaceIds), date_from: from, date_to: to, page, page_size: PAGE_SIZE })
    items.push(...res.items)
    total = res.total
    if (res.items.length === 0 || items.length >= total) break
  }
  return { items, total }
}

function Totals({ rows }) {
  const totals = totalsByCurrency(rows)
  if (totals.length === 0) return null
  return (
    <strong data-testid="month-total">
      {totals.map((t, i) => (
        <span key={t.currency}>
          {i > 0 && ' + '}
          {money(t.total, t.currency)}
        </span>
      ))}
    </strong>
  )
}

// Every expense and every income entry of one month, opened by clicking that month on a chart.
// Expenses can be edited or deleted here; onChanged lets the page refresh the charts behind it.
export default function MonthDetailDialog({
  month, scope, spaceIds, onClose, onChangeMonth, options, groups, trips, onChanged,
}) {
  const [state, setState] = useState({ loading: true, loaded: false, error: null, expenses: [], expenseTotal: 0, income: [] })
  const [editing, setEditing] = useState(null) // { id, form }
  const [confirmingId, setConfirmingId] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [expanded, setExpanded] = useState(() => new Set()) // keys of the bills that are open
  const [moveChoice, setMoveChoice] = useState('')
  const [notice, setNotice] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const latest = useRef(0)
  const closeRef = useRef(null)
  const editingRef = useRef(null)
  const viewKey = useRef('')
  const showIncome = includesIncome(scope, spaceIds)
  const idsKey = (spaceIds || []).join(',')
  const spaces = (groups || []).concat(trips || [])
  const opts = { categories: [], shops: [], currencies: [], ...(options || {}) }
  editingRef.current = editing

  useEffect(() => {
    const request = ++latest.current
    // A new month or scope starts from a blank view; a reload after an edit keeps the rows on screen.
    const key = `${month}|${scope}|${idsKey}|${showIncome}`
    const fresh = key !== viewKey.current
    viewKey.current = key
    if (fresh) {
      setEditing(null)
      setConfirmingId(null)
      setActionError(null)
      setSelected(new Set())
      setExpanded(new Set())
      setNotice(null)
    }
    setState((s) => ({ ...s, loading: true, loaded: fresh ? false : s.loaded, error: null }))
    Promise.all([
      loadMonthExpenses(month, scope, spaceIds),
      showIncome ? fetchIncome() : Promise.resolve([]),
    ])
      .then(([exp, inc]) => {
        if (request !== latest.current) return
        setState({
          loading: false, loaded: true, error: null, expenses: exp.items, expenseTotal: exp.total, income: incomeInMonth(inc, month),
        })
      })
      .catch((err) => {
        if (request === latest.current) setState((s) => ({ ...s, loading: false, error: err.message || 'Could not load this month.' }))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, scope, idsKey, showIncome, reloadKey])

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      // Escape backs out of an edit first; a second press closes the window.
      if (editingRef.current) setEditing(null)
      else onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const { loading, loaded, error, expenses, expenseTotal, income } = state
  // Items of one receipt show as a single line that opens to its items.
  const billGroups = useMemo(() => groupIntoBills(expenses), [expenses])
  const bills = billGroups.filter((g) => g.items.length > 1)

  async function afterChange() {
    setReloadKey((k) => k + 1)
    if (onChanged) await onChanged()
  }

  async function saveEdit(expense) {
    const { changes, error: problem } = expenseChanges(expense, editing.form)
    if (problem) {
      setActionError(problem)
      return
    }
    if (Object.keys(changes).length === 0) {
      setEditing(null)
      return
    }
    setBusy(true)
    setActionError(null)
    try {
      await updateExpense(expense.id, changes)
      setEditing(null)
      await afterChange()
    } catch (err) {
      setActionError(err.message || 'Could not save the change.')
    } finally {
      setBusy(false)
    }
  }

  async function removeExpense(expense) {
    setBusy(true)
    setActionError(null)
    try {
      await deleteExpense(expense.id)
      setConfirmingId(null)
      await afterChange()
    } catch (err) {
      setActionError(err.message || 'Could not delete the expense.')
    } finally {
      setBusy(false)
    }
  }

  const trips_ = movableTrips(trips)
  const editable = expenses.filter((e) => canEditExpense(e, spaces))
  const allSelected = editable.length > 0 && editable.every((e) => selected.has(e.id))
  const tripCategory = tripCategoryIds(expenses).filter((id) => editable.some((e) => e.id === id))

  const toggle = (id) =>
    setSelected((cur) => {
      const next = new Set(cur)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleOpen = (key) =>
    setExpanded((cur) => {
      const next = new Set(cur)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  // The box on a bill's line picks (or clears) all of its items at once.
  const toggleBill = (ids) =>
    setSelected((cur) => {
      const next = new Set(cur)
      const all = ids.every((id) => next.has(id))
      ids.forEach((id) => (all ? next.delete(id) : next.add(id)))
      return next
    })

  async function moveSelected() {
    const changes = moveChanges(moveChoice)
    if (!changes || selected.size === 0) return
    const ids = [...selected]
    setBusy(true)
    setActionError(null)
    try {
      await bulkUpdateExpenses({ ids, changes })
      setSelected(new Set())
      setMoveChoice('')
      setNotice(movedMessage(ids.length, moveChoice, trips_))
      await afterChange()
    } catch (err) {
      setActionError(err.message || 'Could not move the expenses.')
    } finally {
      setBusy(false)
    }
  }

  async function copySelected() {
    const changes = moveChanges(moveChoice)
    if (!changes || changes.group_id === null || selected.size === 0) return
    setBusy(true)
    setActionError(null)
    try {
      const result = await bulkCopyExpenses({ ids: [...selected], group_id: changes.group_id })
      setSelected(new Set())
      setMoveChoice('')
      setNotice(copiedMessage(result, moveChoice, trips_))
      await afterChange()
    } catch (err) {
      setActionError(err.message || 'Could not copy the expenses.')
    } finally {
      setBusy(false)
    }
  }

  const renderExpense = (e, inBill) =>
                    editing?.id === e.id ? (
                        <tr key={e.id} className="editing">
                          <td colSpan={7}>
                            <div className="edit-grid">
                              <label className="edit-field">
                                <span>Date</span>
                                <input type="date" value={editing.form.date} onChange={(ev) => setField('date')(ev.target.value)} />
                              </label>
                              <label className="edit-field edit-field--wide">
                                <span>Description</span>
                                <input type="text" value={editing.form.description} onChange={(ev) => setField('description')(ev.target.value)} />
                              </label>
                              <label className="edit-field">
                                <span>Shop</span>
                                <input type="text" list="month-detail-shops" value={editing.form.shop} onChange={(ev) => setField('shop')(ev.target.value)} />
                              </label>
                              <label className="edit-field">
                                <span>Category</span>
                                <input type="text" list="month-detail-categories" value={editing.form.category} onChange={(ev) => setField('category')(ev.target.value)} />
                              </label>
                              <label className="edit-field">
                                <span>Amount</span>
                                <input type="number" step="0.01" min="0.01" value={editing.form.amount} onChange={(ev) => setField('amount')(ev.target.value)} />
                              </label>
                              <label className="edit-field">
                                <span>Currency</span>
                                <CurrencySelect value={editing.form.currency} onChange={setField('currency')} currencies={opts.currencies} allowDefault={false} />
                              </label>
                            </div>
                            <div className="edit-actions">
                              <button type="button" className="icon-btn save" disabled={busy} onClick={() => saveEdit(e)}>✓ Save</button>
                              <button type="button" className="icon-btn" disabled={busy} onClick={() => { setEditing(null); setActionError(null) }}>✕ Cancel</button>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        <tr key={e.id} className={inBill ? 'bill-item' : undefined}>
                          <td>
                            {canEditExpense(e, spaces) && (
                              <input
                                type="checkbox"
                                aria-label={`Select ${e.description || e.category}`}
                                checked={selected.has(e.id)}
                                onChange={() => toggle(e.id)}
                              />
                            )}
                          </td>
                          <td>{e.date}</td>
                          <td>{e.description}</td>
                          <td>{e.shop}</td>
                          <td>
                            {e.category}
                            {spaceName(e, spaces) && <span className="month-detail-space">🧳 {spaceName(e, spaces)}</span>}
                          </td>
                          <td className="num">{money(e.amount, e.currency)}</td>
                          <td className="right nowrap">
                            {canEditExpense(e, spaces) &&
                              (confirmingId === e.id ? (
                                <>
                                  <span className="month-detail-confirm">Delete?</span>
                                  <button type="button" className="delete-btn" disabled={busy} onClick={() => removeExpense(e)}>Yes</button>
                                  <button type="button" className="icon-btn" disabled={busy} onClick={() => setConfirmingId(null)}>No</button>
                                </>
                              ) : (
                                <>
                                  <button
                                    type="button"
                                    className="icon-btn"
                                    title="Edit"
                                    aria-label={`Edit ${e.description || e.category}`}
                                    onClick={() => { setEditing({ id: e.id, form: editFormFor(e) }); setConfirmingId(null); setActionError(null) }}
                                  >
                                    ✎
                                  </button>
                                  <button
                                    type="button"
                                    className="delete-btn"
                                    title="Delete"
                                    aria-label={`Delete ${e.description || e.category}`}
                                    onClick={() => { setConfirmingId(e.id); setEditing(null); setActionError(null) }}
                                  >
                                    ✕
                                  </button>
                                </>
                              ))}
                          </td>
                        </tr>
                      )

  const setField = (field) => (value) => setEditing((cur) => ({ ...cur, form: { ...cur.form, [field]: value } }))
  const canGoNext = shiftMonth(month, 1) <= currentMonthKey()

  return (
    <div className="month-detail-backdrop" onClick={onClose}>
      <div
        className="month-detail"
        role="dialog"
        aria-modal="true"
        aria-label={`Expenses and income for ${monthTitle(month)}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="month-detail-head">
          <button type="button" aria-label="Previous month" onClick={() => onChangeMonth(shiftMonth(month, -1))}>‹</button>
          <h2>{monthTitle(month)}</h2>
          <button type="button" aria-label="Next month" disabled={!canGoNext} onClick={() => onChangeMonth(shiftMonth(month, 1))}>›</button>
          <button type="button" ref={closeRef} className="month-detail-close" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        {loading && !loaded && <p className="subtitle">Loading…</p>}
        {error && <p className="subtitle" role="alert">Couldn’t load this month: {error}</p>}
        {actionError && <p className="subtitle month-detail-error" role="alert">{actionError}</p>}

        {loaded && !error && (
          <>
            <datalist id="month-detail-categories">
              {opts.categories.map((c) => <option key={c} value={c} />)}
            </datalist>
            <datalist id="month-detail-shops">
              {opts.shops.map((c) => <option key={c} value={c} />)}
            </datalist>
            <h3>
              Expenses ({expenseTotal}) <Totals rows={expenses} />
            </h3>
            {notice && <p className="subtitle month-detail-notice" role="status">{notice}</p>}
            {expenses.length > 0 && editable.length > 0 && (
              <div className="month-detail-bulk">
                {tripCategory.length > 0 && (
                  <button type="button" className="icon-btn" onClick={() => setSelected(new Set(tripCategory))}>
                    Select the {tripCategory.length} categorised Trip
                  </button>
                )}
                {selected.size > 0 && (
                  <>
                    <span>{selected.size} selected</span>
                    <select aria-label="Trip" value={moveChoice} onChange={(ev) => setMoveChoice(ev.target.value)}>
                      <option value="">Choose a trip…</option>
                      {trips_.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                      <option value="personal">Back to personal (no trip)</option>
                    </select>
                    <button type="button" className="icon-btn save" disabled={busy || !moveChoice} onClick={moveSelected}>
                      Move {selected.size}
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      title="Adds a copy in the trip and keeps the original. Both count in your spending."
                      disabled={busy || !moveChoice || moveChoice === 'personal'}
                      onClick={copySelected}
                    >
                      Copy {selected.size}
                    </button>
                    <button type="button" className="icon-btn" disabled={busy} onClick={() => setSelected(new Set())}>Clear</button>
                  </>
                )}
              </div>
            )}
            {bills.length > 0 && (
              <div className="month-detail-bulk">
                <button type="button" className="icon-btn" onClick={() => setExpanded(new Set(bills.map((g) => g.key)))}>
                  Expand all {bills.length} bills
                </button>
                <button type="button" className="icon-btn" disabled={expanded.size === 0} onClick={() => setExpanded(new Set())}>
                  Collapse all
                </button>
              </div>
            )}
            {expenses.length === 0 ? (
              <p className="subtitle">No expenses this month.</p>
            ) : (
              <div className="month-detail-scroll">
                <table className="table" data-testid="month-expenses">
                  <thead>
                    <tr>
                      <th>
                        <input
                          type="checkbox"
                          aria-label="Select all expenses"
                          checked={allSelected}
                          disabled={editable.length === 0}
                          onChange={() => setSelected(allSelected ? new Set() : new Set(editable.map((e) => e.id)))}
                        />
                      </th>
                      <th>Date</th><th>Description</th><th>Shop</th><th>Category</th><th className="num">Amount</th><th /></tr>
                  </thead>
                  <tbody>
                    {billGroups.map((group) => {
                      if (group.items.length === 1) return renderExpense(group.items[0], false)
                      const open = expanded.has(group.key)
                      const ids = group.items.filter((e) => canEditExpense(e, spaces)).map((e) => e.id)
                      const picked = ids.filter((id) => selected.has(id)).length
                      const total = billTotal(group.items)
                      const name = group.shop || group.items[0].description
                      return (
                        <Fragment key={group.key}>
                          <tr className="bill-header">
                            <td>
                              {ids.length > 0 && (
                                <input
                                  type="checkbox"
                                  aria-label={`Select all items of ${name}`}
                                  checked={picked === ids.length}
                                  ref={(el) => { if (el) el.indeterminate = picked > 0 && picked < ids.length }}
                                  onChange={() => toggleBill(ids)}
                                />
                              )}
                            </td>
                            <td>{group.date}</td>
                            <td>
                              <button
                                type="button"
                                className="bill-toggle"
                                aria-expanded={open}
                                aria-label={`${open ? 'Hide' : 'Show'} the ${group.items.length} items of ${name}`}
                                onClick={() => toggleOpen(group.key)}
                              >
                                {open ? '▾' : '▸'} {group.items.length} items
                              </button>
                            </td>
                            <td>{group.shop}</td>
                            <td>
                              {categorySummary(group.items)}
                              {spaceName(group.items[0], spaces) && (
                                <span className="month-detail-space">🧳 {spaceName(group.items[0], spaces)}</span>
                              )}
                            </td>
                            <td className="num">{money(total.total, total.currency)}</td>
                            <td />
                          </tr>
                          {open && group.items.map((e) => renderExpense(e, true))}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {expenseTotal > expenses.length && (
              <p className="subtitle">Showing the latest {expenses.length} of {expenseTotal} expenses. Use Spending to see them all.</p>
            )}

            {showIncome ? (
              <>
                <h3>
                  Income ({income.length}) <Totals rows={income} />
                </h3>
                {income.length === 0 ? (
                  <p className="subtitle">No income this month.</p>
                ) : (
                  <div className="month-detail-scroll">
                    <table className="table" data-testid="month-income">
                      <thead>
                        <tr><th>Date</th><th>Source</th><th>Note</th><th className="num">Amount</th></tr>
                      </thead>
                      <tbody>
                        {income.map((r) => (
                          <tr key={r.id}>
                            <td>{r.date}</td>
                            <td>{r.source}</td>
                            <td>{r.note}</td>
                            <td className="num">{money(r.amount, r.currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <p className="subtitle">Income is personal, so it isn’t shown for a shared space.</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

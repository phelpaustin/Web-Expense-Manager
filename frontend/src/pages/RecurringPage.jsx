import { Fragment, useState } from 'react'
import { FREQUENCIES } from '../constants.js'
import { money } from '../format.js'

const today = () => new Date().toISOString().slice(0, 10)

export default function RecurringPage({
  recurring,
  recurringForm,
  setRecurringForm,
  savingRecurring,
  onAdd,
  onApply,
  onApplyDue,
  onDelete,
  onUpdate,
  onBackfill,
}) {
  const [expandedId, setExpandedId] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [backfillForm, setBackfillForm] = useState(null)
  const [busy, setBusy] = useState(false)

  function toggleExpand(t) {
    if (expandedId === t.id) {
      setExpandedId(null)
      return
    }
    setExpandedId(t.id)
    setEditForm({ item: t.item, category: t.category, amount: t.amount, frequency: t.frequency, auto_post: t.auto_post })
    setBackfillForm({ start_date: '', end_date: today(), amount: t.amount })
  }

  async function handleSaveEdit(e, id) {
    e.preventDefault()
    setBusy(true)
    try {
      await onUpdate(id, {
        item: editForm.item,
        category: editForm.category,
        amount: parseFloat(editForm.amount),
        frequency: editForm.frequency,
        auto_post: editForm.auto_post,
      })
    } finally {
      setBusy(false)
    }
  }

  async function handleSaveBackfill(e, id) {
    e.preventDefault()
    setBusy(true)
    try {
      await onBackfill(id, {
        start_date: backfillForm.start_date,
        end_date: backfillForm.end_date || undefined,
        amount: backfillForm.amount === '' ? undefined : parseFloat(backfillForm.amount),
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1 className="page-title">🔁 Recurring</h1>

      <section className="panel">
        <h2>➕ Add recurring template</h2>
        <form className="add-form" onSubmit={onAdd}>
          <input
            type="text"
            placeholder="Item (e.g. Netflix)"
            required
            value={recurringForm.item}
            onChange={(e) => setRecurringForm({ ...recurringForm, item: e.target.value })}
          />
          <input
            type="text"
            placeholder="Category"
            value={recurringForm.category}
            onChange={(e) => setRecurringForm({ ...recurringForm, category: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={recurringForm.amount}
            onChange={(e) => setRecurringForm({ ...recurringForm, amount: e.target.value })}
          />
          <select
            value={recurringForm.frequency}
            onChange={(e) => setRecurringForm({ ...recurringForm, frequency: e.target.value })}
          >
            {FREQUENCIES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={recurringForm.auto_post}
              onChange={(e) => setRecurringForm({ ...recurringForm, auto_post: e.target.checked })}
            />
            Auto-post
          </label>
          <button type="submit" disabled={savingRecurring}>
            {savingRecurring ? 'Saving…' : 'Add'}
          </button>
        </form>

        {recurring.some((t) => t.due) && (
          <button className="apply-due-btn" onClick={onApplyDue}>
            ⏰ Apply all due ({recurring.filter((t) => t.due).length})
          </button>
        )}

        {recurring.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Frequency</th>
                <th>Last applied</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {recurring.map((t) => (
                <Fragment key={t.id}>
                  <tr>
                    <td>
                      {t.item} {t.due && <span className="due-badge">DUE</span>}
                    </td>
                    <td>{t.category}</td>
                    <td>{t.frequency}</td>
                    <td>{t.last_applied || 'Never'}</td>
                    <td className="right">{money(t.amount)}</td>
                    <td className="right nowrap">
                      <button className="icon-btn" onClick={() => onApply(t.id)} title="Apply now">
                        ➕
                      </button>
                      <button className="ghost-btn" onClick={() => toggleExpand(t)} title="Backfill history / edit">
                        {expandedId === t.id ? 'Close' : 'Manage'}
                      </button>
                      <button className="delete-btn" onClick={() => onDelete(t.id)} title="Delete">
                        ✕
                      </button>
                    </td>
                  </tr>
                  {expandedId === t.id && (
                    <tr>
                      <td colSpan={6}>
                        <div className="recurring-detail">
                          <div>
                            <h3>📅 Backfill history</h3>
                            <p className="subtitle">
                              Add past occurrences that happened before this template was tracked (e.g. rent paid
                              monthly for the last year). Run it again with a later start date and a new amount to
                              record a rate change partway through.
                            </p>
                            <form className="add-form" onSubmit={(e) => handleSaveBackfill(e, t.id)}>
                              <label>
                                From
                                <input
                                  type="date"
                                  required
                                  max={today()}
                                  value={backfillForm.start_date}
                                  onChange={(e) => setBackfillForm({ ...backfillForm, start_date: e.target.value })}
                                />
                              </label>
                              <label>
                                Through
                                <input
                                  type="date"
                                  max={today()}
                                  value={backfillForm.end_date}
                                  onChange={(e) => setBackfillForm({ ...backfillForm, end_date: e.target.value })}
                                />
                              </label>
                              <input
                                type="number"
                                step="0.01"
                                min="0.01"
                                placeholder={`Amount (default ${t.amount})`}
                                value={backfillForm.amount}
                                onChange={(e) => setBackfillForm({ ...backfillForm, amount: e.target.value })}
                              />
                              <button type="submit" disabled={busy}>
                                {busy ? 'Adding…' : 'Add history'}
                              </button>
                            </form>
                          </div>

                          <div>
                            <h3>✏️ Edit template</h3>
                            <p className="subtitle">
                              Changing the amount only affects future applications — past expenses keep the amount
                              they were posted with.
                            </p>
                            <form className="add-form" onSubmit={(e) => handleSaveEdit(e, t.id)}>
                              <input
                                type="text"
                                required
                                value={editForm.item}
                                onChange={(e) => setEditForm({ ...editForm, item: e.target.value })}
                              />
                              <input
                                type="text"
                                placeholder="Category"
                                value={editForm.category}
                                onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                              />
                              <input
                                type="number"
                                step="0.01"
                                min="0.01"
                                required
                                value={editForm.amount}
                                onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })}
                              />
                              <select
                                value={editForm.frequency}
                                onChange={(e) => setEditForm({ ...editForm, frequency: e.target.value })}
                              >
                                {FREQUENCIES.map((f) => (
                                  <option key={f} value={f}>
                                    {f}
                                  </option>
                                ))}
                              </select>
                              <label className="checkbox-label">
                                <input
                                  type="checkbox"
                                  checked={editForm.auto_post}
                                  onChange={(e) => setEditForm({ ...editForm, auto_post: e.target.checked })}
                                />
                                Auto-post
                              </label>
                              <button type="submit" disabled={busy}>
                                {busy ? 'Saving…' : 'Save'}
                              </button>
                            </form>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}

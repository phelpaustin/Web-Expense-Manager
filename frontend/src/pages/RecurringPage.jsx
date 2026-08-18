import { FREQUENCIES } from '../constants.js'
import { money } from '../format.js'

export default function RecurringPage({
  recurring,
  recurringForm,
  setRecurringForm,
  savingRecurring,
  onAdd,
  onApply,
  onApplyDue,
  onDelete,
}) {
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
                <tr key={t.id}>
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
                    <button className="delete-btn" onClick={() => onDelete(t.id)} title="Delete">
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}

import { useEffect, useState } from 'react'
import {
  fetchExpenses,
  fetchSummary,
  fetchTrends,
  fetchCategories,
  fetchBudgetStatus,
  createExpense,
  updateExpense,
  deleteExpense,
  setBudget,
  deleteBudget,
  fetchIncome,
  fetchIncomeSummary,
  createIncome,
  deleteIncome,
  fetchRecurring,
  createRecurring,
  deleteRecurring,
  applyRecurring,
  applyDueRecurring,
  fetchMe,
  getToken,
  logout,
} from './api/client.js'
import AuthScreen from './AuthScreen.jsx'

const STATUS_COLORS = {
  ok: '#22c55e',
  caution: '#f59e0b',
  warning: '#f97316',
  exceeded: '#ef4444',
}

const FREQUENCIES = ['Daily', 'Weekly', 'Bi-weekly', 'Monthly', 'Quarterly', 'Yearly']

const EMPTY_FORM = { date: '', category: '', description: '', amount: '' }
const EMPTY_INCOME = { date: '', source: '', note: '', amount: '' }
const EMPTY_RECURRING = { item: '', category: '', amount: '', frequency: 'Monthly', auto_post: false }

export default function App() {
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [expenses, setExpenses] = useState([])
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState(null)
  const [categories, setCategories] = useState([])
  const [budgets, setBudgets] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [income, setIncome] = useState([])
  const [incomeSummary, setIncomeSummary] = useState(null)
  const [incomeForm, setIncomeForm] = useState(EMPTY_INCOME)
  const [savingIncome, setSavingIncome] = useState(false)
  const [recurring, setRecurring] = useState([])
  const [recurringForm, setRecurringForm] = useState(EMPTY_RECURRING)
  const [savingRecurring, setSavingRecurring] = useState(false)

  function loadAll() {
    return Promise.all([
      fetchExpenses(),
      fetchSummary(),
      fetchTrends(),
      fetchCategories(),
      fetchBudgetStatus(),
      fetchIncome(),
      fetchIncomeSummary(),
      fetchRecurring(),
    ])
      .then(([exp, sum, tr, cat, bud, inc, incSum, rec]) => {
        setExpenses(exp)
        setSummary(sum)
        setTrends(tr)
        setCategories(cat)
        setBudgets(bud)
        setIncome(inc)
        setIncomeSummary(incSum)
        setRecurring(rec)
        setError(null)
      })
      .catch((err) => setError(err.message))
  }

  // On mount, if a token exists, verify it and load the user's data.
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true)
      setLoading(false)
      return
    }
    fetchMe()
      .then((me) => {
        setUser(me)
        return loadAll()
      })
      .catch(() => {
        logout()
      })
      .finally(() => {
        setAuthChecked(true)
        setLoading(false)
      })
  }, [])

  function handleAuthed() {
    setLoading(true)
    fetchMe()
      .then((me) => {
        setUser(me)
        return loadAll()
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  function handleLogout() {
    logout()
    setUser(null)
    setExpenses([])
    setSummary(null)
    setTrends(null)
    setCategories([])
    setBudgets([])
    setIncome([])
    setIncomeSummary(null)
    setRecurring([])
  }

  async function handleAdd(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await createExpense({
        date: form.date,
        category: form.category,
        description: form.description,
        amount: parseFloat(form.amount),
      })
      setForm(EMPTY_FORM)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    try {
      await deleteExpense(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEdit(expense) {
    setEditingId(expense.id)
    setEditForm({
      date: expense.date,
      category: expense.category,
      description: expense.description,
      amount: String(expense.amount),
    })
  }

  function cancelEdit() {
    setEditingId(null)
    setEditForm(EMPTY_FORM)
  }

  async function saveEdit(id) {
    try {
      await updateExpense(id, {
        date: editForm.date,
        category: editForm.category,
        description: editForm.description,
        amount: parseFloat(editForm.amount),
      })
      cancelEdit()
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSetBudget(category, amount) {
    const value = parseFloat(amount)
    if (!value || value <= 0) return
    try {
      await setBudget(category, value)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteBudget(category) {
    try {
      await deleteBudget(category)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddIncome(e) {
    e.preventDefault()
    setSavingIncome(true)
    try {
      await createIncome({
        date: incomeForm.date,
        amount: parseFloat(incomeForm.amount),
        source: incomeForm.source,
        note: incomeForm.note,
      })
      setIncomeForm(EMPTY_INCOME)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingIncome(false)
    }
  }

  async function handleDeleteIncome(id) {
    try {
      await deleteIncome(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddRecurring(e) {
    e.preventDefault()
    setSavingRecurring(true)
    try {
      await createRecurring({
        item: recurringForm.item,
        category: recurringForm.category,
        amount: parseFloat(recurringForm.amount),
        frequency: recurringForm.frequency,
        auto_post: recurringForm.auto_post,
      })
      setRecurringForm(EMPTY_RECURRING)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingRecurring(false)
    }
  }

  async function handleApplyRecurring(id) {
    try {
      await applyRecurring(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleApplyDue() {
    try {
      await applyDueRecurring()
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteRecurring(id) {
    try {
      await deleteRecurring(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="container">
      {!authChecked ? (
        <p>Loading…</p>
      ) : !user ? (
        <AuthScreen onAuthed={handleAuthed} />
      ) : (
        <>
          <header className="app-header">
            <div>
              <h1>💳 Expense Dashboard</h1>
              <p className="subtitle">Signed in as {user.email}</p>
            </div>
            <button className="logout-btn" onClick={handleLogout}>
              Log out
            </button>
          </header>

          {loading && <p>Loading…</p>}

          {error && (
            <div className="error">
              <strong>Something went wrong.</strong>
              <p>{error}</p>
            </div>
          )}

      {summary && (
        <section className="cards">
          <div className="card">
            <span className="card-label">Total spent</span>
            <span className="card-value">${summary.total.toFixed(2)}</span>
          </div>
          <div className="card">
            <span className="card-label">Transactions</span>
            <span className="card-value">{summary.count}</span>
          </div>
          <div className="card">
            <span className="card-label">Categories</span>
            <span className="card-value">{Object.keys(summary.by_category).length}</span>
          </div>
        </section>
      )}

      {incomeSummary && (
        <section className="cards income-cards">
          <div className="card">
            <span className="card-label">Income this month</span>
            <span className="card-value">${incomeSummary.this_month.toFixed(2)}</span>
          </div>
          <div className="card">
            <span className="card-label">Avg income / month</span>
            <span className="card-value">${incomeSummary.avg_month.toFixed(2)}</span>
          </div>
          <div className="card">
            <span className="card-label">Total income</span>
            <span className="card-value">${incomeSummary.total.toFixed(2)}</span>
          </div>
          {summary && (
            <div className="card">
              <span className="card-label">Net this month</span>
              <span className="card-value">
                ${(incomeSummary.this_month - summary.total).toFixed(2)}
              </span>
            </div>
          )}
        </section>
      )}

      <section className="panel">
        <h2>💵 Add income (ported from income_manager.py)</h2>
        <form className="add-form" onSubmit={handleAddIncome}>
          <input
            type="date"
            required
            value={incomeForm.date}
            onChange={(e) => setIncomeForm({ ...incomeForm, date: e.target.value })}
          />
          <input
            type="text"
            placeholder="Source (e.g. Salary)"
            required
            value={incomeForm.source}
            onChange={(e) => setIncomeForm({ ...incomeForm, source: e.target.value })}
          />
          <input
            type="text"
            placeholder="Note (optional)"
            value={incomeForm.note}
            onChange={(e) => setIncomeForm({ ...incomeForm, note: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={incomeForm.amount}
            onChange={(e) => setIncomeForm({ ...incomeForm, amount: e.target.value })}
          />
          <button type="submit" disabled={savingIncome}>
            {savingIncome ? 'Saving…' : 'Add'}
          </button>
        </form>

        {income.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Source</th>
                <th>Note</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {income.map((i) => (
                <tr key={i.id}>
                  <td>{i.date}</td>
                  <td>{i.source}</td>
                  <td>{i.note}</td>
                  <td className="right">${i.amount.toFixed(2)}</td>
                  <td className="right">
                    <button
                      className="delete-btn"
                      onClick={() => handleDeleteIncome(i.id)}
                      title="Delete"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>🔁 Recurring (ported from recurring_manager.py)</h2>
        <form className="add-form" onSubmit={handleAddRecurring}>
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
          <button className="apply-due-btn" onClick={handleApplyDue}>
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
                  <td className="right">${t.amount.toFixed(2)}</td>
                  <td className="right nowrap">
                    <button
                      className="icon-btn"
                      onClick={() => handleApplyRecurring(t.id)}
                      title="Apply now"
                    >
                      ➕
                    </button>
                    <button
                      className="delete-btn"
                      onClick={() => handleDeleteRecurring(t.id)}
                      title="Delete"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>➕ Add expense</h2>
        <form className="add-form" onSubmit={handleAdd}>
          <input
            type="date"
            required
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
          <input
            type="text"
            placeholder="Category"
            required
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          />
          <input
            type="text"
            placeholder="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Add'}
          </button>
        </form>
      </section>

      {budgets.length > 0 && (
        <section className="panel">
          <h2>🎯 Budget status (ported from budget_manager.py)</h2>
          {budgets.map((b) => {
            const key = b.category === 'Total' ? '__total_monthly__' : b.category
            return (
              <div key={b.category} className={b.category === 'Total' ? 'budget-row total' : 'budget-row'}>
                <span className="budget-name">{b.category}</span>
                <div className="cat-bar-track">
                  <div
                    className="cat-bar-fill"
                    style={{
                      width: `${Math.min(b.pct, 100)}%`,
                      background: STATUS_COLORS[b.status] || '#64748b',
                    }}
                  />
                </div>
                <span className="budget-pct" style={{ color: STATUS_COLORS[b.status] }}>
                  {b.pct}%
                </span>
                <span className="budget-amt">${b.spent.toFixed(2)} spent</span>
                <input
                  className="budget-input"
                  type="number"
                  step="1"
                  min="1"
                  defaultValue={b.budget}
                  title="Budget amount — edit and press Enter"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') e.currentTarget.blur()
                  }}
                  onBlur={(e) => {
                    const v = parseFloat(e.target.value)
                    if (v && v !== b.budget) handleSetBudget(key, v)
                  }}
                />
                <button
                  className="delete-btn"
                  onClick={() => handleDeleteBudget(key)}
                  title="Delete budget"
                >
                  ✕
                </button>
              </div>
            )
          })}
        </section>
      )}

      {trends && (
        <section className="panel">
          <h2>📈 Trends (ported from analytics.py)</h2>
          <div className="trend-row">
            {trends.monthly.map((m) => (
              <div key={m.month} className="trend-cell">
                <span className="card-label">{m.month}</span>
                <span className="trend-value">${m.total.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div className="trend-meta">
            {trends.change && (
              <span>
                vs previous month:{' '}
                <strong className={trends.change.direction === 'up' ? 'up' : 'down'}>
                  {trends.change.direction === 'up' ? '▲' : '▼'} {Math.abs(trends.change.pct_change)}%
                </strong>
              </span>
            )}
            {trends.forecast_next_month != null && (
              <span>
                forecast next month: <strong>${trends.forecast_next_month.toFixed(2)}</strong>
              </span>
            )}
          </div>
        </section>
      )}

      {categories.length > 0 && (
        <section className="panel">
          <h2>🏆 Category breakdown</h2>
          {categories.map((c) => (
            <div key={c.category} className="cat-row">
              <span className="cat-name">{c.category}</span>
              <div className="cat-bar-track">
                <div className="cat-bar-fill" style={{ width: `${c.pct_of_total}%` }} />
              </div>
              <span className="cat-pct">{c.pct_of_total}%</span>
              <span className="cat-amt">${c.total.toFixed(2)}</span>
            </div>
          ))}
        </section>
      )}

      {expenses.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Category</th>
              <th>Description</th>
              <th className="right">Amount</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((e) =>
              editingId === e.id ? (
                <tr key={e.id} className="editing">
                  <td>
                    <input
                      type="date"
                      value={editForm.date}
                      onChange={(ev) => setEditForm({ ...editForm, date: ev.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={editForm.category}
                      onChange={(ev) => setEditForm({ ...editForm, category: ev.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={editForm.description}
                      onChange={(ev) => setEditForm({ ...editForm, description: ev.target.value })}
                    />
                  </td>
                  <td className="right">
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      className="amount-input"
                      value={editForm.amount}
                      onChange={(ev) => setEditForm({ ...editForm, amount: ev.target.value })}
                    />
                  </td>
                  <td className="right nowrap">
                    <button className="icon-btn save" onClick={() => saveEdit(e.id)} title="Save">
                      ✓
                    </button>
                    <button className="icon-btn" onClick={cancelEdit} title="Cancel">
                      ✕
                    </button>
                  </td>
                </tr>
              ) : (
                <tr key={e.id}>
                  <td>{e.date}</td>
                  <td>{e.category}</td>
                  <td>{e.description}</td>
                  <td className="right">${e.amount.toFixed(2)}</td>
                  <td className="right nowrap">
                    <button className="icon-btn" onClick={() => startEdit(e)} title="Edit">
                      ✎
                    </button>
                    <button className="delete-btn" onClick={() => handleDelete(e.id)} title="Delete">
                      ✕
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      )}
        </>
      )}
    </div>
  )
}

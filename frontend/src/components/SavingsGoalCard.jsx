import { useState } from 'react'
import CurrencySelect from './CurrencySelect.jsx'
import {
  addSavingsContribution, deleteSavingsContribution, deleteSavingsGoal, fetchSavingsGoal, updateSavingsGoal,
} from '../api/client.js'
import { barPercent, contributionBody, contributionText, daysLeftText, formatDate, goalBody, paceText, savedText, statusInfo, todayLocal } from '../savings.js'

// One goal: its progress, what it needs, and the things you do to it (add or take out money, see the
// history, edit, delete). Every change asks the page to reload the list, so the order and the numbers
// always come from the server.
export default function SavingsGoalCard({ goal, currencies, onChanged, onDeleted }) {
  const [mode, setMode] = useState(null) // null | 'add' | 'history' | 'edit'
  const [history, setHistory] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [kind, setKind] = useState('deposit')
  const [money, setMoney] = useState({ amount: '', date: todayLocal(), note: '' })
  const [edit, setEdit] = useState(null)
  const status = statusInfo(goal.status)

  function open(next) {
    setError(null)
    if (mode === next) return setMode(null)
    setMode(next)
    if (next === 'history') {
      fetchSavingsGoal(goal.id)
        .then((g) => setHistory(g.contributions))
        .catch((err) => setError(err.message))
    }
    if (next === 'edit') {
      setEdit({ name: goal.name, target: String(goal.target_amount), currency: goal.currency, targetDate: goal.target_date || '', note: goal.note || '' })
    }
    if (next === 'add') setMoney({ amount: '', date: todayLocal(), note: '' })
  }

  async function run(action, after) {
    setBusy(true)
    setError(null)
    try {
      const result = await action()
      if (after) after(result)
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function submitMoney(e) {
    e.preventDefault()
    const { body, error: problem } = contributionBody({ kind, ...money })
    if (problem) return setError(problem)
    run(() => addSavingsContribution(goal.id, body), (g) => {
      setHistory(g.contributions)
      setMoney({ amount: '', date: todayLocal(), note: '' })
      setMode(null)
    })
  }

  function submitEdit(e) {
    e.preventDefault()
    const { body, error: problem } = goalBody(edit, { includeCurrency: goal.contribution_count === 0 })
    if (problem) return setError(problem)
    run(() => updateSavingsGoal(goal.id, body), () => setMode(null))
  }

  function removeContribution(c) {
    run(() => deleteSavingsContribution(goal.id, c.id), (g) => setHistory(g.contributions))
  }

  function removeGoal() {
    const n = goal.contribution_count
    const detail = n ? ` and its ${n} ${n === 1 ? 'deposit or withdrawal' : 'deposits and withdrawals'}` : ''
    if (!window.confirm(`Delete “${goal.name}”${detail}?`)) return
    setBusy(true)
    setError(null)
    deleteSavingsGoal(goal.id)
      .then(() => onDeleted(goal.id))
      .catch((err) => {
        setError(err.message)
        setBusy(false)
      })
  }

  return (
    <section className="panel savings-goal" data-testid={`goal-${goal.id}`}>
      <div className="savings-head">
        <h2>{goal.name}</h2>
        <span className={`savings-status savings-${status.tone}`}>{status.label}</span>
      </div>
      {goal.note && <p className="subtitle savings-note">{goal.note}</p>}

      <div
        className="savings-track"
        role="progressbar"
        aria-label={`${goal.name} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, Math.round(goal.pct))}
      >
        <div className={`savings-fill savings-fill-${status.tone}`} style={{ width: `${barPercent(goal)}%` }} />
      </div>
      <div className="savings-figures">
        <strong>{savedText(goal)}</strong>
        <span>{goal.pct}%</span>
      </div>
      <p className="savings-pace">{paceText(goal)}</p>
      {goal.target_date && (
        <p className="subtitle savings-date">
          Target date {formatDate(goal.target_date)}
          {daysLeftText(goal) && ` · ${daysLeftText(goal)}`}
        </p>
      )}

      <div className="savings-actions">
        <button type="button" className="ghost-btn" aria-expanded={mode === 'add'} onClick={() => open('add')}>
          Add or take out money
        </button>
        <button type="button" className="ghost-btn" aria-expanded={mode === 'history'} onClick={() => open('history')}>
          History ({goal.contribution_count})
        </button>
        <button type="button" className="ghost-btn" aria-expanded={mode === 'edit'} onClick={() => open('edit')}>
          Edit
        </button>
        <button type="button" className="ghost-btn savings-delete" disabled={busy} onClick={removeGoal}>
          Delete
        </button>
      </div>

      {error && <p className="savings-error" role="alert">{error}</p>}

      {mode === 'add' && (
        <form className="add-form savings-form" onSubmit={submitMoney} aria-label={`Add money to ${goal.name}`}>
          <div className="report-toggle" role="group" aria-label="Deposit or withdrawal">
            <button type="button" aria-pressed={kind === 'deposit'} className={kind === 'deposit' ? 'active' : ''} onClick={() => setKind('deposit')}>
              Add
            </button>
            <button type="button" aria-pressed={kind === 'withdraw'} className={kind === 'withdraw' ? 'active' : ''} onClick={() => setKind('withdraw')}>
              Take out
            </button>
          </div>
          <input
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0.01"
            aria-label="Amount"
            placeholder={`Amount (${goal.currency})`}
            value={money.amount}
            onChange={(e) => setMoney({ ...money, amount: e.target.value })}
          />
          <input type="date" aria-label="Date" value={money.date} max={todayLocal()} onChange={(e) => setMoney({ ...money, date: e.target.value })} />
          <input type="text" aria-label="Note" placeholder="Note (optional)" maxLength={1000} value={money.note} onChange={(e) => setMoney({ ...money, note: e.target.value })} />
          <button type="submit" className="primary-btn" disabled={busy}>
            Save
          </button>
        </form>
      )}

      {mode === 'edit' && edit && (
        <form className="add-form savings-form" onSubmit={submitEdit} aria-label={`Edit ${goal.name}`}>
          <input type="text" aria-label="Goal name" maxLength={120} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
          <input
            type="number" inputMode="decimal" step="0.01" min="0.01" aria-label="Target amount"
            value={edit.target} onChange={(e) => setEdit({ ...edit, target: e.target.value })}
          />
          <CurrencySelect
            value={edit.currency}
            onChange={(c) => setEdit({ ...edit, currency: c })}
            currencies={currencies}
            allowDefault={false}
            disabled={goal.contribution_count > 0}
            title={goal.contribution_count > 0 ? 'The currency can’t change once money has been added' : 'Currency'}
          />
          <input type="date" aria-label="Target date" value={edit.targetDate} onChange={(e) => setEdit({ ...edit, targetDate: e.target.value })} />
          <input type="text" aria-label="Goal note" placeholder="Note (optional)" maxLength={1000} value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} />
          <button type="submit" className="primary-btn" disabled={busy}>
            Save
          </button>
        </form>
      )}

      {mode === 'history' && (
        <div className="savings-history">
          {history === null && !error && <p className="subtitle">Loading…</p>}
          {history && history.length === 0 && <p className="subtitle">Nothing added yet.</p>}
          {history && history.length > 0 && (
            <ul>
              {history.map((c) => (
                <li key={c.id}>
                  <span className={Number(c.amount) < 0 ? 'up' : ''}>{contributionText(c, goal.currency)}</span>
                  <button type="button" className="delete-btn" disabled={busy} aria-label={`Remove ${contributionText(c, goal.currency)}`} onClick={() => removeContribution(c)}>
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

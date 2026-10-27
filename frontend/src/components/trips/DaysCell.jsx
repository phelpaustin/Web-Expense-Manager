import { useState } from 'react'
import { updateExpense } from '../../api/client.js'
import { dayLabel, daysLabel, isPlaced, coveredDates } from '../../tripDays.js'
import './tripDays.css'

// The "Days" cell of a trip expense: which trip day(s) it covers, with a small editor.
export default function DaysCell({ expense, days, canEdit, onSaved, onError }) {
  const [editing, setEditing] = useState(false)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [busy, setBusy] = useState(false)

  if (days.length === 0) return <span className="muted">—</span>
  const hasDays = Boolean(expense.covers_from && expense.covers_to)
  const placed = isPlaced(expense, days)

  function open() {
    const dates = coveredDates(expense)
    const numberOf = (date) => days.find((d) => d.date === date)?.n
    const first = numberOf(dates[0]) ?? 1
    const last = numberOf(dates[dates.length - 1]) ?? first
    setFrom(String(first))
    setTo(String(last))
    setEditing(true)
  }

  const pickFrom = (value) => {
    setFrom(value)
    if (Number(to) < Number(value)) setTo(value) // the end can't be before the start
  }

  async function save(changes) {
    setBusy(true)
    try {
      await updateExpense(expense.id, changes)
      setEditing(false)
      await onSaved()
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  const day = (n) => days.find((d) => d.n === Number(n))
  const saveRange = () => save({ covers_from: day(from).date, covers_to: day(to).date })

  if (editing) {
    return (
      <span className="trip-days-editor">
        <select aria-label="From day" value={from} onChange={(e) => pickFrom(e.target.value)}>
          {days.map((d) => (
            <option key={d.n} value={d.n}>{dayLabel(d)}</option>
          ))}
        </select>
        to
        <select aria-label="To day" value={to} onChange={(e) => setTo(e.target.value)}>
          {days.filter((d) => d.n >= Number(from)).map((d) => (
            <option key={d.n} value={d.n}>{dayLabel(d)}</option>
          ))}
        </select>
        <button type="button" className="icon-btn" disabled={busy} onClick={() => { setFrom('1'); setTo(String(days.length)) }}>
          Whole trip
        </button>
        <button type="button" className="icon-btn save" disabled={busy} onClick={saveRange}>✓ Save</button>
        {hasDays && (
          <button type="button" className="icon-btn" disabled={busy} onClick={() => save({ covers_from: null, covers_to: null })}>
            Clear
          </button>
        )}
        <button type="button" className="icon-btn" disabled={busy} onClick={() => setEditing(false)}>✕</button>
      </span>
    )
  }

  return (
    <span className="trip-days-cell">
      {placed ? daysLabel(expense, days) : <span className="muted">{daysLabel(expense, days)} · not on a trip day</span>}
      {canEdit && (
        <button type="button" className="icon-btn" title="Choose the trip day or days" aria-label={`Set days for ${expense.description || expense.shop || expense.category}`} onClick={open}>
          ✎
        </button>
      )}
    </span>
  )
}

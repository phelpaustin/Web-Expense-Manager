import { useEffect, useRef, useState } from 'react'
import { SPACE_TYPE_ICONS } from './shared.jsx'
import './tripPick.css'

// Move or copy one expense, or every item of one bill, into a trip or space. Opened by the ✈ buttons.
export default function TripPickPanel({ pick, allSpaces, busy, onRun, onCancel }) {
  const [target, setTarget] = useState('')
  const panelRef = useRef(null)
  const selectRef = useRef(null)

  useEffect(() => {
    panelRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
    selectRef.current?.focus()
  }, [])

  // Trips first: that is what this is mostly used for.
  const spaces = allSpaces
    .filter((g) => g.role !== 'viewer')
    .sort((a, b) => (b.space_type === 'trip') - (a.space_type === 'trip'))
  const count = pick.ids.length

  return (
    <section className="panel trip-pick" ref={panelRef} aria-label="Move or copy to a trip">
      <h2>✈️ Move or copy to a trip</h2>
      <p className="trip-pick-what">
        {pick.label} · {count} item{count === 1 ? '' : 's'}
      </p>
      <div className="edit-actions">
        <select aria-label="Trip or space" ref={selectRef} value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Choose a trip or space…</option>
          {spaces.map((g) => (
            <option key={g.id} value={g.id}>
              {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
            </option>
          ))}
          <option value="personal">Personal expenses (no trip)</option>
        </select>
        <button type="button" className="primary-btn" disabled={busy || !target} onClick={() => onRun('move', target)}>
          Move
        </button>
        <button
          type="button"
          className="icon-btn"
          disabled={busy || !target || target === 'personal'}
          onClick={() => onRun('copy', target)}
        >
          Copy
        </button>
        <button type="button" className="icon-btn" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
      <p className="subtitle">
        Move takes it out of your personal expenses and into the trip. Copy keeps the original and adds a copy in the trip,
        so both count in your spending.
      </p>
    </section>
  )
}

import { useState } from 'react'
import { tripChanges, tripFormFor } from '../../tripEdit.js'

// Edit a trip's name, destination, dates, budget and currency, inside its card.
export default function TripEditForm({ trip, onSave, onCancel }) {
  const [form, setForm] = useState(() => tripFormFor(trip))
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (field) => (e) => setForm((cur) => ({ ...cur, [field]: e.target.value }))
  const datesChanged = form.start_date !== (trip.start_date || '') || form.end_date !== (trip.end_date || '')

  async function submit(e) {
    e.preventDefault()
    const { changes, error: problem } = tripChanges(trip, form)
    if (problem) {
      setError(problem)
      return
    }
    if (Object.keys(changes).length === 0) {
      onCancel()
      return
    }
    setBusy(true)
    setError(null)
    try {
      await onSave(changes)
    } catch (err) {
      setError(err.message || 'Could not save the trip.')
      setBusy(false)
    }
  }

  return (
    <form className="trip-edit-form" onSubmit={submit} noValidate aria-label={`Edit ${trip.name}`}>
      <div className="edit-grid">
        <label className="edit-field edit-field--wide">
          <span>Trip name</span>
          <input type="text" required value={form.name} onChange={set('name')} />
        </label>
        <label className="edit-field edit-field--wide">
          <span>Destination</span>
          <input type="text" value={form.destination} onChange={set('destination')} />
        </label>
        <label className="edit-field">
          <span>Start date</span>
          <input type="date" value={form.start_date} onChange={set('start_date')} />
        </label>
        <label className="edit-field">
          <span>End date</span>
          <input type="date" min={form.start_date || undefined} value={form.end_date} onChange={set('end_date')} />
        </label>
        <label className="edit-field">
          <span>Budget (optional)</span>
          <input type="number" step="0.01" min="0.01" value={form.budget} onChange={set('budget')} />
        </label>
        <label className="edit-field">
          <span>Currency</span>
          <input type="text" maxLength={3} value={form.currency} onChange={set('currency')} />
        </label>
      </div>
      {datesChanged && (
        <p className="subtitle trip-edit-note">
          Days you have set on expenses stay on their real dates, so some may fall outside the new dates. They then show
          under “Not on a trip day”.
        </p>
      )}
      {error && (
        <p role="alert" className="trip-edit-error">
          {error}
        </p>
      )}
      <div className="edit-actions">
        <button type="submit" className="primary-btn" disabled={busy}>
          {busy ? 'Saving…' : 'Save trip'}
        </button>
        <button type="button" className="ghost-btn" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

import { useState } from 'react'
import { money } from '../format.js'
import { fetchTripSummary, fetchTripExpenses } from '../api/client.js'

const STATUSES = ['Planned', 'Active', 'Completed']
const EMPTY_TRIP = { name: '', destination: '', start_date: '', end_date: '', budget: '', currency: 'SEK', status: 'Planned' }

export default function TripsPage({ trips, onAddTrip, onUpdateTrip, onDeleteTrip, onError }) {
  const [form, setForm] = useState(EMPTY_TRIP)
  const [expandedId, setExpandedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    await onAddTrip({
      name: form.name,
      destination: form.destination,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      budget: form.budget ? parseFloat(form.budget) : null,
      currency: form.currency || 'SEK',
      status: form.status,
    })
    setForm(EMPTY_TRIP)
  }

  async function toggleExpand(trip) {
    if (expandedId === trip.id) {
      setExpandedId(null)
      setDetail(null)
      return
    }
    setExpandedId(trip.id)
    setLoadingDetail(true)
    try {
      const [summary, expenses] = await Promise.all([fetchTripSummary(trip.id), fetchTripExpenses(trip.id)])
      setDetail({ summary, expenses })
    } catch (err) {
      onError(err.message)
    } finally {
      setLoadingDetail(false)
    }
  }

  function handleStatusChange(trip, status) {
    onUpdateTrip(trip.id, { status })
  }

  return (
    <>
      <h1 className="page-title">🧳 Trips</h1>

      <section className="panel">
        <h2>➕ New trip</h2>
        <form className="add-form" onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Trip name"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            type="text"
            placeholder="Destination"
            value={form.destination}
            onChange={(e) => setForm({ ...form, destination: e.target.value })}
          />
          <input
            type="date"
            title="Start date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
          />
          <input
            type="date"
            title="End date"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Budget (optional)"
            value={form.budget}
            onChange={(e) => setForm({ ...form, budget: e.target.value })}
          />
          <input
            type="text"
            className="unit-input"
            placeholder="Cur"
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value })}
          />
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button type="submit">Add trip</button>
        </form>
      </section>

      {trips.length === 0 ? (
        <p className="subtitle">No trips yet — add one above to start tagging expenses to it.</p>
      ) : (
        <div className="trip-list">
          {trips.map((t) => (
            <section key={t.id} className="panel trip-card">
              <div className="trip-card-header" onClick={() => toggleExpand(t)}>
                <div>
                  <h2 style={{ margin: 0 }}>
                    {t.name}
                    {t.destination ? ` — ${t.destination}` : ''}
                  </h2>
                  <p className="subtitle">
                    {t.start_date || '—'} to {t.end_date || '—'}
                    {t.budget ? ` · Budget ${money(t.budget)}` : ''}
                  </p>
                </div>
                <div className="trip-card-actions" onClick={(e) => e.stopPropagation()}>
                  <select value={t.status} onChange={(e) => handleStatusChange(t, e.target.value)}>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <button className="delete-btn" onClick={() => onDeleteTrip(t.id)} title="Delete trip">
                    ✕
                  </button>
                </div>
              </div>

              {expandedId === t.id && (
                <div className="trip-detail">
                  {loadingDetail && <p className="subtitle">Loading…</p>}
                  {detail && (
                    <>
                      <div className="trip-summary-row">
                        <span>
                          Spent: <strong>{money(detail.summary.total_spent)}</strong>
                        </span>
                        {detail.summary.budget && (
                          <span>
                            Remaining: <strong>{money(detail.summary.remaining)}</strong>
                          </span>
                        )}
                        <span>{detail.summary.expense_count} expense(s)</span>
                      </div>
                      {Object.keys(detail.summary.by_category).length > 0 && (
                        <ul className="trip-category-list">
                          {Object.entries(detail.summary.by_category).map(([cat, amt]) => (
                            <li key={cat}>
                              {cat}: {money(amt)}
                            </li>
                          ))}
                        </ul>
                      )}
                      {detail.expenses.length > 0 && (
                        <table className="table">
                          <thead>
                            <tr>
                              <th>Date</th>
                              <th>Category</th>
                              <th>Shop</th>
                              <th>Description</th>
                              <th className="right">Amount</th>
                            </tr>
                          </thead>
                          <tbody>
                            {detail.expenses.map((e) => (
                              <tr key={e.id}>
                                <td>{e.date}</td>
                                <td>{e.category}</td>
                                <td>{e.shop}</td>
                                <td>{e.description}</td>
                                <td className="right">{money(e.amount)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </>
                  )}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </>
  )
}

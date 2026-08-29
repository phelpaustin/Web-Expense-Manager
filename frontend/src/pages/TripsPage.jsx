import { useState } from 'react'
import { money } from '../format.js'
import {
  fetchTripSummary,
  fetchTripExpenses,
  fetchGroupMembers,
  inviteToGroup,
  removeGroupMember,
  cancelGroupInvite,
  setMyMapping,
} from '../api/client.js'

const STATUSES = ['Planned', 'Active', 'Completed']
const EMPTY_TRIP = {
  name: '',
  destination: '',
  start_date: '',
  end_date: '',
  budget: '',
  currency: 'SEK',
  status: 'Planned',
  parent_group_id: '',
}

export default function TripsPage({ trips, groups, onAddTrip, onUpdateTrip, onDeleteTrip, onRefresh, onError }) {
  const [form, setForm] = useState(EMPTY_TRIP)
  const [expandedId, setExpandedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [members, setMembers] = useState([])
  const [inviteEmail, setInviteEmail] = useState('')
  const [localName, setLocalName] = useState('')
  const [localParent, setLocalParent] = useState('')

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
      parent_group_id: form.parent_group_id ? parseInt(form.parent_group_id, 10) : null,
    })
    setForm(EMPTY_TRIP)
  }

  async function loadDetail(trip) {
    setLoadingDetail(true)
    try {
      const [summary, expenses, mem] = await Promise.all([
        fetchTripSummary(trip.id),
        fetchTripExpenses(trip.id),
        fetchGroupMembers(trip.id),
      ])
      setDetail({ summary, expenses })
      setMembers(mem)
      setLocalName(trip.local_name || '')
      setLocalParent(trip.local_parent_group_id ? String(trip.local_parent_group_id) : '')
    } catch (err) {
      onError(err.message)
    } finally {
      setLoadingDetail(false)
    }
  }

  function toggleExpand(trip) {
    if (expandedId === trip.id) {
      setExpandedId(null)
      setDetail(null)
      setMembers([])
      return
    }
    setExpandedId(trip.id)
    loadDetail(trip)
  }

  function handleStatusChange(trip, status) {
    onUpdateTrip(trip.id, { status })
  }

  async function handleInvite(e, tripId) {
    e.preventDefault()
    if (!inviteEmail.trim()) return
    try {
      await inviteToGroup(tripId, inviteEmail.trim())
      setInviteEmail('')
      setMembers(await fetchGroupMembers(tripId))
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleRemoveMember(tripId, userId) {
    try {
      await removeGroupMember(tripId, userId)
      setMembers(await fetchGroupMembers(tripId))
      await onRefresh()
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleCancelInvite(tripId, email) {
    try {
      await cancelGroupInvite(tripId, email)
      setMembers(await fetchGroupMembers(tripId))
    } catch (err) {
      onError(err.message)
    }
  }

  async function handleSaveMapping(tripId) {
    try {
      await setMyMapping(tripId, {
        localName: localName.trim(),
        localParentGroupId: localParent ? parseInt(localParent, 10) : null,
      })
      await onRefresh()
    } catch (err) {
      onError(err.message)
    }
  }

  return (
    <>
      <h1 className="page-title">🧳 Trips</h1>
      <p className="subtitle">
        A trip is its own Expense Space — optionally filed under another space — that you can share with just the
        people going, without giving them access to anything else.
      </p>

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
          {groups && groups.length > 0 && (
            <select
              value={form.parent_group_id}
              onChange={(e) => setForm({ ...form, parent_group_id: e.target.value })}
              title="File this trip under one of your Expense Spaces (optional)"
            >
              <option value="">No parent space</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  Under: {g.name}
                </option>
              ))}
            </select>
          )}
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
                    ✈️ {t.name}
                    {t.destination ? ` — ${t.destination}` : ''}
                  </h2>
                  <p className="subtitle">
                    {t.start_date || '—'} to {t.end_date || '—'}
                    {t.budget ? ` · Budget ${money(t.budget)}` : ''} · {t.member_count} member
                    {t.member_count === 1 ? '' : 's'} · <span className={`role-badge role-${t.role}`}>{t.role}</span>
                  </p>
                </div>
                <div className="trip-card-actions" onClick={(e) => e.stopPropagation()}>
                  {t.role === 'owner' ? (
                    <>
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
                    </>
                  ) : (
                    <span className="subtitle">{t.status}</span>
                  )}
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

                      <h3>👥 Who's on this trip</h3>
                      <ul className="member-list">
                        {members.map((m) => (
                          <li key={m.user_id ?? m.email}>
                            <span>
                              {m.role === 'invited' ? '✉️' : '👤'} {m.name || m.email}
                              {m.role !== 'invited' && m.name ? ` (${m.email})` : ''}
                            </span>
                            <span className={`role-badge role-${m.role}`}>{m.role}</span>
                            {t.role === 'owner' && m.role === 'member' && (
                              <button className="delete-btn" onClick={() => handleRemoveMember(t.id, m.user_id)} title="Remove">
                                ✕
                              </button>
                            )}
                            {t.role === 'owner' && m.role === 'invited' && (
                              <button
                                className="delete-btn"
                                onClick={() => handleCancelInvite(t.id, m.email)}
                                title="Cancel invite"
                              >
                                ✕
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                      {t.role === 'owner' && (
                        <form className="add-form" onSubmit={(e) => handleInvite(e, t.id)}>
                          <input
                            type="email"
                            placeholder="Invite by email — only they'll see this trip"
                            value={inviteEmail}
                            onChange={(e) => setInviteEmail(e.target.value)}
                          />
                          <button type="submit">Invite</button>
                        </form>
                      )}

                      {t.role !== 'owner' && (
                        <>
                          <h3>🗂️ File this trip on your side</h3>
                          <p className="subtitle">
                            Give it your own name and/or park it under one of your own Expense Spaces — this only
                            changes how it looks for you.
                          </p>
                          <div className="add-form">
                            <input
                              type="text"
                              placeholder="Your name for this trip (optional)"
                              value={localName}
                              onChange={(e) => setLocalName(e.target.value)}
                            />
                            {groups && groups.length > 0 && (
                              <select value={localParent} onChange={(e) => setLocalParent(e.target.value)}>
                                <option value="">No parent space</option>
                                {groups.map((g) => (
                                  <option key={g.id} value={g.id}>
                                    Under: {g.name}
                                  </option>
                                ))}
                              </select>
                            )}
                            <button type="button" onClick={() => handleSaveMapping(t.id)}>
                              Save
                            </button>
                          </div>
                        </>
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

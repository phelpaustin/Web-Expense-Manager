import { useEffect, useRef, useState } from 'react'
import CurrencySelect from '../components/CurrencySelect.jsx'
import SavingsGoalCard from '../components/SavingsGoalCard.jsx'
import { createSavingsGoal, fetchSavingsGoals } from '../api/client.js'
import { goalBody, summaryText } from '../savings.js'

const EMPTY = { name: '', target: '', currency: '', targetDate: '', note: '' }

// Things you are saving towards: a target, optionally by a date, and the money you put aside for it.
// The app tracks what you tell it; it doesn't move or look at any money.
export default function SavingsPage({ currencies = [], baseCurrency }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState(null)
  const [busy, setBusy] = useState(false)
  const latest = useRef(0)

  // Only the newest request may update the page.
  function load() {
    const request = ++latest.current
    return fetchSavingsGoals()
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }

  useEffect(() => {
    load()
  }, [])

  function submit(e) {
    e.preventDefault()
    const { body, error: problem } = goalBody(form)
    if (problem) return setFormError(problem)
    setBusy(true)
    setFormError(null)
    createSavingsGoal(body)
      .then(() => {
        setForm(EMPTY)
        setCreating(false)
        return load()
      })
      .catch((err) => setFormError(err.message))
      .finally(() => setBusy(false))
  }

  function removed(id) {
    setData((d) => (d ? { ...d, goals: d.goals.filter((g) => g.id !== id) } : d))
    load()
  }

  const atLimit = data && data.goals.length >= data.limit
  const header = (
    <div className="period-header">
      <h1 className="page-title">🎯 Savings</h1>
      <button type="button" className="primary-btn" disabled={atLimit} aria-expanded={creating} onClick={() => setCreating((v) => !v)}>
        {creating ? 'Cancel' : '➕ New goal'}
      </button>
    </div>
  )

  if (error && !data) {
    return (
      <>
        {header}
        <p className="subtitle">Couldn’t load your savings goals: {error}</p>
      </>
    )
  }
  if (!data || !Array.isArray(data.goals)) {
    return (
      <>
        {header}
        <p className="subtitle">Loading…</p>
      </>
    )
  }

  return (
    <>
      {header}
      <p className="subtitle">
        Set a target for something you’re saving up for, then add money as you put it aside. This tracks what you enter; it doesn’t move any money.
      </p>
      {atLimit && <p className="subtitle">You’ve reached the limit of {data.limit} goals.</p>}

      {creating && (
        <section className="panel">
          <h2>New savings goal</h2>
          <form className="add-form savings-form" onSubmit={submit} aria-label="New savings goal">
            <input type="text" aria-label="Goal name" placeholder="What are you saving for?" maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input
              type="number" inputMode="decimal" step="0.01" min="0.01" aria-label="Target amount" placeholder="Target amount"
              value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}
            />
            <CurrencySelect value={form.currency} onChange={(c) => setForm({ ...form, currency: c })} currencies={currencies} defaultCurrency={baseCurrency} />
            <label className="savings-date-field">
              Target date (optional)
              <input type="date" aria-label="Target date" value={form.targetDate} onChange={(e) => setForm({ ...form, targetDate: e.target.value })} />
            </label>
            <input type="text" aria-label="Goal note" placeholder="Note (optional)" maxLength={1000} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            <button type="submit" className="primary-btn" disabled={busy}>
              Create goal
            </button>
          </form>
          {formError && <p className="savings-error" role="alert">{formError}</p>}
        </section>
      )}

      {summaryText(data.summary) && <p className="subtitle" data-testid="savings-summary">{summaryText(data.summary)}</p>}

      {data.goals.length === 0 && !creating && (
        <section className="panel">
          <p>No savings goals yet. Start with something you’re saving for: a trip, a rainy-day fund, a new laptop.</p>
        </section>
      )}

      {data.goals.map((g) => (
        <SavingsGoalCard key={g.id} goal={g} currencies={currencies} onChanged={load} onDeleted={removed} />
      ))}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </>
  )
}

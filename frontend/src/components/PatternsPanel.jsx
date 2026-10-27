import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchPatterns } from '../api/client.js'
import { WINDOWS, describeRow, headline, notEnoughText, rowLabel, withBars } from '../patterns.js'

// "When you spend": the average per calendar day for each weekday and for each part of the month.
// Averaged per day, not per expense, so a month with five Saturdays doesn't make Saturday look busier.
// Recurring payments are left out: they land on their due date by design.
export default function PatternsPanel({ scope, spaceIds, refreshKey }) {
  const [months, setMonths] = useState(6)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)

  useEffect(() => {
    const request = ++latest.current
    fetchPatterns({ months, scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
    // spaceIds is a fresh array each render; the scope key in the parent remounts on a real change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [months, scope, refreshKey])

  const heading = (
    <div className="period-header">
      <h2>🗓️ When you spend</h2>
      <select aria-label="Spending pattern window" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
        {WINDOWS.map((w) => (
          <option key={w.months} value={w.months}>
            {w.label}
          </option>
        ))}
      </select>
    </div>
  )

  if (error && !data) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Couldn’t load this: {error}</p>
      </section>
    )
  }
  if (!data || !Array.isArray(data.weekdays) || !Array.isArray(data.month_parts)) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const lead = headline(data)
  const table = (rows, label, noun) => (
    <table className="table">
      <thead>
        <tr>
          <th>{label}</th>
          <th>A day, on average</th>
          <th className="right">Share</th>
        </tr>
      </thead>
      <tbody>
        {withBars(rows).map((r) => (
          <tr key={rowLabel(r)} aria-label={describeRow(r, noun)}>
            <td>{rowLabel(r)}</td>
            <td className="pattern-bar-cell">
              <div className={r.peak && data.enough ? 'pattern-bar pattern-bar-peak' : 'pattern-bar'} style={{ width: `${r.percent}%` }} />
              <div className="subtitle">{money(r.per_day)}</div>
            </td>
            <td className="right">{r.share_pct}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <section className="panel">
      {heading}
      {lead && <p>{lead}</p>}
      {!data.enough && <p className="subtitle">{notEnoughText(data)}</p>}
      {table(data.weekdays, 'Weekday', 'weekday')}
      {table(data.month_parts, 'Part of the month', 'monthly')}
      <p className="subtitle">Recurring payments are left out, since they fall on their due date.</p>
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </section>
  )
}

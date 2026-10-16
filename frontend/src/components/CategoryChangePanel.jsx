import { useEffect, useRef, useState } from 'react'
import { BarChart, Bar, Cell, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { money } from '../format.js'
import { fetchCategoryChange } from '../api/client.js'
import { buildWaterfall, describeChange, monthLabel, signedMoney } from '../categoryChange.js'

// Spending going up is red and going down is green, matching the rest of the dashboard.
const COLORS = { total: '#6d7bff', up: '#f87171', down: '#10b981' }
const axis = { stroke: '#9aa3b8', fontSize: 12 }

function shorten(name) {
  return name.length > 12 ? `${name.slice(0, 11)}…` : name
}

function StepTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const step = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{step.name}</div>
      <div style={{ color: COLORS[step.kind] }}>{step.kind === 'total' ? money(step.amount) : signedMoney(step.amount)}</div>
    </div>
  )
}

function currentMonthKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function monthOptions(data) {
  const all = new Set([...data.months, data.month])
  return [...all].sort().reverse()
}

// "Why did spending change?": the month's change against the month before, broken down by
// category. Defaults to the last finished month, the same pair behind "vs previous month".
export default function CategoryChangePanel({ scope, spaceIds, refreshKey }) {
  const [month, setMonth] = useState(null) // null = let the server pick the default
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')

  // Reload on a new month or scope, and whenever the dashboard's data was refreshed
  // (refreshKey). Only the newest request may update the view.
  useEffect(() => {
    const request = ++latest.current
    fetchCategoryChange({ month, scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [month, scope, idsKey, refreshKey])

  if (error && !data) {
    return (
      <section className="panel">
        <h2>🔍 What changed</h2>
        <p className="subtitle">Couldn’t load the category breakdown: {error}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="panel">
        <h2>🔍 What changed</h2>
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const rows = [...data.categories, ...(data.other ? [{ category: `${data.other.count} other${data.other.count === 1 ? '' : 's'}`, ...data.other }] : [])]

  return (
    <section className="panel">
      <h2>🔍 What changed</h2>
      <label style={{ display: 'block', marginBottom: '0.75rem' }}>
        Month{' '}
        <select aria-label="Month" value={data.month} onChange={(e) => setMonth(e.target.value)}>
          {monthOptions(data).map((m) => (
            <option key={m} value={m}>
              {monthLabel(m)}
              {m === currentMonthKey() ? ' (so far)' : ''}
            </option>
          ))}
        </select>
      </label>

      <p data-testid="change-sentence">{describeChange(data)}</p>

      {data.available && data.categories.length > 0 && (
        <>
          <div data-testid="change-chart">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={buildWaterfall(data)} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
                <XAxis dataKey="name" {...axis} interval={0} tickFormatter={shorten} />
                <YAxis {...axis} width={52} />
                <Tooltip content={<StepTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
                <Bar dataKey="value" stackId="w" isAnimationActive={false}>
                  {buildWaterfall(data).map((step, i) => (
                    <Cell key={i} fill={COLORS[step.kind]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className="table">
            <thead>
              <tr>
                <th>Category</th>
                <th className="right">{monthLabel(data.compare_month)}</th>
                <th className="right">{monthLabel(data.month)}</th>
                <th className="right">Change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.category}>
                  <td>
                    {r.category}
                    {r.status === 'new' && <span className="subtitle"> (new)</span>}
                    {r.status === 'stopped' && <span className="subtitle"> (none this month)</span>}
                  </td>
                  <td className="right">{money(r.before)}</td>
                  <td className="right">{money(r.now)}</td>
                  <td className={`right ${Number(r.change) > 0 ? 'up' : 'down'}`}>
                    {signedMoney(r.change)}
                    {r.pct_change != null && ` (${r.pct_change > 0 ? '+' : ''}${r.pct_change}%)`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.unchanged_count > 0 && (
            <p className="subtitle">
              {data.unchanged_count} {data.unchanged_count === 1 ? 'category' : 'categories'} unchanged.
            </p>
          )}
        </>
      )}

      {data.unconverted_count > 0 && (
        <p className="subtitle">
          {data.unconverted_count} {data.unconverted_count === 1 ? 'expense' : 'expenses'} in a currency without an exchange rate{' '}
          {data.unconverted_count === 1 ? 'is' : 'are'} left out.
        </p>
      )}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </section>
  )
}

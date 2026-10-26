import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchPeriodCompare } from '../api/client.js'
import { monthLabel } from '../categoryChange.js'
import { comparedWith, describeRow, partialNote, pctText } from '../periodCompare.js'

function currentMonthKey() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// "How does this month compare?": against last month, the same month last year and your usual
// (3-month average). Spending going up is red and going down is green, as everywhere else.
// `month` is chosen on the page (null = the server picks the last finished month) so the movers below follow it.
export default function PeriodComparePanel({ month = null, onMonthChange, scope, spaceIds, refreshKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')

  useEffect(() => {
    const request = ++latest.current
    fetchPeriodCompare({ month, scope, spaceIds })
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
        <h2>⚖️ Compared with</h2>
        <p className="subtitle">Couldn’t load the comparison: {error}</p>
      </section>
    )
  }
  if (!data || !Array.isArray(data.comparisons)) {
    return (
      <section className="panel">
        <h2>⚖️ Compared with</h2>
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const months = [...new Set([...(data.months || []), data.month])].sort().reverse()

  return (
    <section className="panel">
      <div className="period-header">
        <h2>⚖️ Compared with</h2>
        <label>
          Month{' '}
          <select aria-label="Compare month" value={data.month} onChange={(e) => onMonthChange?.(e.target.value)}>
            {months.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m)}
                {m === currentMonthKey() ? ' (so far)' : ''}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="compare-total">
        <strong>{money(data.total)}</strong> spent in {monthLabel(data.month)}
        {data.partial ? ' so far' : ''}.
      </p>

      <div className="compare-grid">
        {data.comparisons.map((row) => (
          <div key={row.key} className="compare-tile" aria-label={describeRow(row, data.total)} role="group">
            <span className="card-label">{row.label}</span>
            {row.available ? (
              <>
                <span className={`compare-pct ${Number(row.change) > 0 ? 'up' : Number(row.change) < 0 ? 'down' : ''}`}>
                  {Number(row.change) === 0 ? 'No change' : pctText(row) || (Number(row.change) > 0 ? '▲' : '▼')}
                </span>
                <span className="subtitle">
                  {money(row.before)} in {comparedWith(row)}
                </span>
              </>
            ) : (
              <>
                <span className="compare-pct">–</span>
                <span className="subtitle">Not enough history yet</span>
              </>
            )}
          </div>
        ))}
      </div>

      {data.partial && <p className="subtitle">{partialNote(data)}</p>}
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

import { useEffect, useRef, useState } from 'react'
import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { money } from '../format.js'
import { fetchSpendingMix } from '../api/client.js'
import {
  MONTH_CHOICES, DEFAULT_MONTHS, MIX_COLORS, chartRows, describeMix, describeOneOff, describeCommitment, describeRule,
} from '../spendingMix.js'

const axis = { stroke: '#9aa3b8', fontSize: 12 }

function MixTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{row.name}{row.partial ? ' (so far)' : ''}</div>
      <div style={{ color: MIX_COLORS.committed }}>Committed: {money(row.committed)}</div>
      <div style={{ color: MIX_COLORS.everyday }}>Everyday: {money(row.everyday)}</div>
      <div style={{ color: MIX_COLORS.oneOff }}>One-offs: {money(row.oneOff)}</div>
      <div>Total: {money(row.total)}</div>
    </div>
  )
}

const LEGEND = [
  ['committed', 'Committed (recurring)'],
  ['everyday', 'Everyday'],
  ['oneOff', 'One-offs'],
]

// Fixed vs everyday vs one-off spending by month, with what a typical month costs and the
// purchases that stood out.
export default function SpendingMixPanel({ scope, spaceIds, refreshKey, onSelectMonth }) {
  const [months, setMonths] = useState(DEFAULT_MONTHS)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')

  // Reload on a new period or scope, and whenever the dashboard's data was refreshed
  // (refreshKey). Only the newest request may update the view.
  useEffect(() => {
    const request = ++latest.current
    fetchSpendingMix({ months, scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [months, scope, idsKey, refreshKey])

  if (error && !data) {
    return (
      <section className="panel">
        <h2>🧱 Committed vs everyday</h2>
        <p className="subtitle">Couldn’t load the spending breakdown: {error}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="panel">
        <h2>🧱 Committed vs everyday</h2>
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const rows = data.available ? chartRows(data) : []

  return (
    <section className="panel">
      <h2>🧱 Committed vs everyday</h2>
      <label style={{ display: 'block', marginBottom: '0.75rem' }}>
        Period{' '}
        <select aria-label="Months shown" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {MONTH_CHOICES.map((c) => (
            <option key={c.months} value={c.months}>
              {c.label}
            </option>
          ))}
        </select>
      </label>

      <p data-testid="mix-sentence">{describeMix(data)}</p>

      {data.available && (
        <>
          <div data-testid="mix-chart">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={rows}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                style={onSelectMonth ? { cursor: 'pointer' } : undefined}
                onClick={
                  onSelectMonth
                    ? (state) => {
                        // Recharts 3 reports the clicked position as an index, not the row.
                        const row = rows[Number(state?.activeTooltipIndex)]
                        if (row?.month) onSelectMonth(row.month)
                      }
                    : undefined
                }
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} width={52} />
                <Tooltip content={<MixTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="committed" stackId="m" fill={MIX_COLORS.committed} isAnimationActive={false} />
                <Bar dataKey="everyday" stackId="m" fill={MIX_COLORS.everyday} isAnimationActive={false} />
                <Bar dataKey="oneOff" stackId="m" fill={MIX_COLORS.oneOff} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="subtitle" data-testid="mix-legend">
            {LEGEND.map(([key, label]) => (
              <span key={key} style={{ marginRight: '1rem' }}>
                <span style={{ color: MIX_COLORS[key] }}>■</span> {label}
              </span>
            ))}
            * month in progress
          </p>
          {onSelectMonth && <p className="chart-hint">Click a month to see its expenses and income.</p>}

          {data.totals.committed_pct != null && (
            <p className="subtitle">
              Over these {data.window.months} months, {data.totals.committed_pct}% of your spending was committed.
            </p>
          )}

          {data.committed_top.length > 0 ? (
            <>
              <h3>Your commitments</h3>
              <ul data-testid="commitments">
                {data.committed_top.map((c) => (
                  <li key={c.template_id}>{describeCommitment(c)}</li>
                ))}
              </ul>
            </>
          ) : (
            <p className="subtitle">
              Nothing counts as committed yet. Recurring items you set up on the Recurring page count once they have been applied.
            </p>
          )}

          {data.one_offs.length > 0 && (
            <>
              <h3>Biggest one-offs</h3>
              <ul data-testid="one-offs">
                {data.one_offs.map((o, i) => (
                  <li key={o.id ?? i}>{describeOneOff(o)}</li>
                ))}
              </ul>
              {data.one_off_count > data.one_offs.length && (
                <p className="subtitle">and {data.one_off_count - data.one_offs.length} more.</p>
              )}
            </>
          )}
          <p className="subtitle">{describeRule(data.rule)}</p>
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

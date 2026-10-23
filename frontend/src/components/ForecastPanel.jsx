import { useEffect, useRef, useState } from 'react'
import { BarChart, Bar, ErrorBar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { money } from '../format.js'
import { fetchForecast } from '../api/client.js'
import { signedMoney } from '../categoryChange.js'
import {
  FORECAST_COLORS, chartRows, describeForecast, describeSoFar, describeAccuracy, describeMethod, describeOneOffs,
  describeCandidate, describeRange,
} from '../forecast.js'

const axis = { stroke: '#9aa3b8', fontSize: 12 }

function ForecastTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{row.name}{row.isForecast ? ' (forecast)' : ''}</div>
      {row.isForecast ? (
        <>
          <div style={{ color: FORECAST_COLORS.forecast }}>About: {money(row.forecast)}</div>
          {row.error && <div>Range: {money(row.forecast - row.error[0])} to {money(row.forecast + row.error[1])}</div>}
        </>
      ) : (
        <>
          <div style={{ color: FORECAST_COLORS.baseline }}>Baseline: {money(row.baseline)}</div>
          {row.oneOff > 0 && <div style={{ color: FORECAST_COLORS.oneOff }}>One-offs: {money(row.oneOff)}</div>}
        </>
      )}
    </div>
  )
}

// What this month is likely to cost, with a range, how well the method has done on past months,
// and a breakdown by category that adds up to the total.
export default function ForecastPanel({ scope, spaceIds, refreshKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')

  // Reload on a new scope and whenever the dashboard's data was refreshed (refreshKey). Only the
  // newest request may update the view.
  useEffect(() => {
    const request = ++latest.current
    fetchForecast({ scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [scope, idsKey, refreshKey])

  if (error && !data) {
    return (
      <section className="panel">
        <h2>🔮 Forecast</h2>
        <p className="subtitle">Couldn’t load the forecast: {error}</p>
      </section>
    )
  }
  if (!data) {
    return (
      <section className="panel">
        <h2>🔮 Forecast</h2>
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>🔮 Forecast</h2>
      <p data-testid="forecast-sentence">{describeForecast(data)}</p>

      {data.available && (
        <>
          <p className="subtitle" data-testid="forecast-sofar">{describeSoFar(data)}</p>
          <p className="subtitle" data-testid="forecast-accuracy">{describeAccuracy(data)}</p>

          <div data-testid="forecast-chart">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartRows(data)} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} width={52} />
                <Tooltip content={<ForecastTooltip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="baseline" stackId="f" fill={FORECAST_COLORS.baseline} isAnimationActive={false} />
                <Bar dataKey="oneOff" stackId="f" fill={FORECAST_COLORS.oneOff} isAnimationActive={false} />
                <Bar dataKey="forecast" stackId="f" fill={FORECAST_COLORS.forecast} isAnimationActive={false}>
                  <ErrorBar dataKey="error" width={6} strokeWidth={2} stroke="#065f46" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="subtitle">
            <span style={{ color: FORECAST_COLORS.baseline }}>■</span> Baseline{' '}
            <span style={{ color: FORECAST_COLORS.oneOff }}>■</span> One-offs{' '}
            <span style={{ color: FORECAST_COLORS.forecast }}>■</span> Forecast (the line shows the range) * month in progress
          </p>

          {data.categories.length > 0 && (
            <>
              <h3>By category</h3>
              <table className="table" data-testid="forecast-categories">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="right">Last month</th>
                    <th className="right">Forecast</th>
                    <th className="right">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((c) => (
                    <tr key={c.category}>
                      <td>{c.category}</td>
                      <td className="right">{money(c.last_month)}</td>
                      <td className="right">{money(c.forecast)}</td>
                      <td className={`right ${Number(c.change) > 0 ? 'up' : Number(c.change) < 0 ? 'down' : ''}`}>{signedMoney(c.change)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <p className="subtitle">{describeOneOffs(data)}</p>

          <details>
            <summary>How was this worked out?</summary>
            <p>{describeMethod(data)}</p>
            {data.candidates.length > 0 && (
              <ul data-testid="forecast-candidates">
                {data.candidates.map((c) => (
                  <li key={c.name}>{describeCandidate(c)}</li>
                ))}
              </ul>
            )}
            {describeRange(data) && <p>{describeRange(data)}</p>}
            <p className="subtitle">
              It forecasts baseline spending (committed and everyday, without one-offs) so one big purchase doesn’t inflate it. Each
              method is tested the way it would really be used: forecast a past month from only the months before it. Seasonal
              patterns are only considered with {data.requirements.months_for_seasons}+ months of history.
              {data.skipped_first_month ? ' Your first month was left out because recording began part-way through it.' : ''}
            </p>
          </details>
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

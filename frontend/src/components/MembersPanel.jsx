import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { money } from '../format.js'
import { fetchMembers } from '../api/client.js'
import {
  DEFAULT_PERIOD, PERIODS, cellAmount, describeBars, memberBars, memberColors, memberLabel, periodRange, spacesText, summaryText, topCategoriesText, trendRows,
} from '../members.js'

const axis = { stroke: '#9aa3b8', fontSize: 12 }

function BarTip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{row.name}</div>
      <div>{money(row.total)}</div>
      <div>{row.share_pct}% of spending</div>
    </div>
  )
}

function TrendTip({ active, payload, label, members, colors }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{label}</div>
      {members.map((m) => (
        <div key={m.user_id} style={{ color: colors.get(m.user_id) }}>
          {memberLabel(m)}: {money(row[`m${m.user_id}`] || 0)}
        </div>
      ))}
      <div>Total: {money(row.total)}</div>
    </div>
  )
}

// Who paid for how much in the shared spaces you pick above: each member's total, share and top
// categories, a member-by-category table and the months side by side. Only spending filed in a
// shared space counts, and every member of a space can already see what is in it.
export default function MembersPanel({ scope, spaceIds, refreshKey }) {
  const [period, setPeriod] = useState(DEFAULT_PERIOD)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')

  useEffect(() => {
    const request = ++latest.current
    fetchMembers({ ...periodRange(period), scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
    // spaceIds is a fresh array each render; idsKey stands for it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, scope, idsKey, refreshKey])

  const heading = (
    <div className="period-header">
      <h2>👥 Spending by member</h2>
      <select aria-label="Members period" value={period} onChange={(e) => setPeriod(e.target.value)}>
        {PERIODS.map((p) => (
          <option key={p.key} value={p.key}>
            {p.label}
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
  if (!data || !Array.isArray(data.members) || !Array.isArray(data.spaces) || !Array.isArray(data.months) || !Array.isArray(data.categories)) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const colors = memberColors(data.members)
  const bars = memberBars(data, colors)
  const trend = trendRows(data)
  const noSpace = data.spaces.length === 0
  const soloNote = !noSpace && data.member_count === 1

  return (
    <>
      <section className="panel">
        {heading}
        {spacesText(data.spaces) && <p className="subtitle">{spacesText(data.spaces)}</p>}
        <p data-testid="members-summary">{summaryText(data)}</p>
        {noSpace && (
          <p className="subtitle">
            Pick a shared space above, or <Link to="/settings?tab=spaces">set one up and invite people</Link>.
          </p>
        )}
        {soloNote && <p className="subtitle">Only you are in {data.spaces.length === 1 ? 'this space' : 'these spaces'} so far.</p>}

        {data.count > 0 && (
          <>
            <div data-testid="members-chart" role="img" aria-label={describeBars(bars)}>
              <ResponsiveContainer width="100%" height={Math.max(120, bars.length * 36 + 20)}>
                <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 20, left: 0, bottom: 4 }}>
                  <XAxis type="number" {...axis} tickFormatter={(v) => Number(v).toLocaleString('en-US')} />
                  <YAxis type="category" dataKey="name" width={120} tickLine={false} {...axis} />
                  <Tooltip content={<BarTip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                  <Bar dataKey="total" isAnimationActive={false} radius={[0, 4, 4, 0]}>
                    {bars.map((b) => (
                      <Cell key={String(b.id)} fill={b.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}

        {data.members.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Member</th>
                <th className="right">Spent</th>
                <th className="right">Share</th>
                <th className="right">Expenses</th>
                <th className="right">Average</th>
                <th>Mostly</th>
              </tr>
            </thead>
            <tbody>
              {data.members.map((m) => (
                <tr key={String(m.user_id)} data-testid={`member-${m.user_id}`}>
                  <td>
                    <span className="member-swatch" style={{ background: colors.get(m.user_id) }} aria-hidden="true" />
                    {memberLabel(m)}
                  </td>
                  <td className="right">{money(m.total)}</td>
                  <td className="right">{m.share_pct}%</td>
                  <td className="right">{m.count}</td>
                  <td className="right">{m.count ? money(m.avg_per_expense) : '–'}</td>
                  <td>{topCategoriesText(m) || '–'}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th>Total</th>
                <th className="right">{money(data.total)}</th>
                <th />
                <th className="right">{data.count}</th>
                <th />
                <th />
              </tr>
            </tfoot>
          </table>
        )}
        {data.unconverted_count > 0 && (
          <p className="subtitle">
            {data.unconverted_count} {data.unconverted_count === 1 ? 'expense is' : 'expenses are'} left out because its currency has no exchange rate.
          </p>
        )}
        {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
      </section>

      {data.categories.length > 0 && data.members.length > 1 && (
        <section className="panel">
          <h2>🧾 Who spends on what</h2>
          <table className="table" data-testid="members-categories">
            <thead>
              <tr>
                <th>Category</th>
                {data.members.map((m) => (
                  <th key={String(m.user_id)} className="right">
                    {memberLabel(m)}
                  </th>
                ))}
                <th className="right">Total</th>
              </tr>
            </thead>
            <tbody>
              {data.categories.map((c) => (
                <tr key={c.category}>
                  <td>{c.other ? `Other (${c.count} categories)` : c.category}</td>
                  {data.members.map((m) => {
                    const v = cellAmount(c, m.user_id)
                    return (
                      <td key={String(m.user_id)} className="right">
                        {v ? money(v) : '–'}
                      </td>
                    )
                  })}
                  <td className="right">{money(c.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {trend.length > 1 && data.members.length > 0 && (
        <section className="panel">
          <h2>📅 Month by month</h2>
          <div data-testid="members-trend">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={trend} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
                <XAxis dataKey="name" {...axis} />
                <YAxis {...axis} width={52} />
                <Tooltip content={<TrendTip members={data.members} colors={colors} />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                {data.members.map((m) => (
                  <Bar key={String(m.user_id)} dataKey={`m${m.user_id}`} stackId="members" fill={colors.get(m.user_id)} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="subtitle" data-testid="members-legend">
            {data.members.map((m) => (
              <span key={String(m.user_id)} style={{ marginRight: '1rem' }}>
                <span style={{ color: colors.get(m.user_id) }}>■</span> {memberLabel(m)}
              </span>
            ))}
          </p>
          {data.months_total > data.months.length && (
            <p className="subtitle">Showing the latest {data.months.length} of {data.months_total} months.</p>
          )}
        </section>
      )}
    </>
  )
}

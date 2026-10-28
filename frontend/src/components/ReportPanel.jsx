import { useEffect, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { money } from '../format.js'
import { downloadReport, fetchReport } from '../api/client.js'
import { useMediaQuery } from '../hooks/useMediaQuery.js'
import { PHONE_QUERY } from './MobileNav.jsx'
import {
  MONTH_NAMES, categoryChartHeight, changeDirection, changeText, chartCategories, describeCategoryChart, describePeriodChart,
  periodChartRows, summaryText, tickLabel, yearChoices,
} from '../report.js'

const axis = { stroke: '#9aa3b8', fontSize: 12 }
const ACCENT = '#6d7bff'
const MUTED = '#c3c8d8'

function AmountTip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const row = payload[0].payload
  return (
    <div className="chart-tip">
      <div className="chart-tip-label">{row.name}</div>
      <div>{money(row.total)}</div>
      {row.share_pct != null && <div>{row.share_pct}% of spending</div>}
      {row.count != null && <div>{row.count} {row.count === 1 ? 'expense' : 'expenses'}</div>}
    </div>
  )
}

// A report for a whole year or one month: totals, spending by category (chart and table), spending over
// the period, top shops and the largest expenses, with the same report as an Excel or PDF download.
export default function ReportPanel({ scope, spaceIds, refreshKey }) {
  const phone = useMediaQuery(PHONE_QUERY)
  const now = new Date()
  const [kind, setKind] = useState('year')
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [downloadError, setDownloadError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')
  const monthArg = kind === 'month' ? month : undefined

  useEffect(() => {
    const request = ++latest.current
    fetchReport({ year, month: monthArg, scope, spaceIds })
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
  }, [year, monthArg, scope, idsKey, refreshKey])

  function download(format) {
    setBusy(format)
    setDownloadError(null)
    downloadReport({ format, year, month: monthArg, scope, spaceIds })
      .catch((err) => setDownloadError(err.message))
      .finally(() => setBusy(null))
  }

  const controls = (
    <div className="report-controls">
      <div className="report-toggle" role="group" aria-label="Report type">
        <button type="button" aria-pressed={kind === 'year'} className={kind === 'year' ? 'active' : ''} onClick={() => setKind('year')}>
          Year
        </button>
        <button type="button" aria-pressed={kind === 'month'} className={kind === 'month' ? 'active' : ''} onClick={() => setKind('month')}>
          Month
        </button>
      </div>
      {kind === 'month' && (
        <select aria-label="Report month" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
          {MONTH_NAMES.map((name, i) => (
            <option key={name} value={i + 1}>
              {name}
            </option>
          ))}
        </select>
      )}
      <select aria-label="Report year" value={year} onChange={(e) => setYear(Number(e.target.value))}>
        {yearChoices(data && data.years, year).map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
      <div className="report-downloads">
        <button type="button" className="ghost-btn" disabled={busy !== null} onClick={() => download('xlsx')}>
          {busy === 'xlsx' ? 'Preparing…' : 'Download Excel'}
        </button>
        <button type="button" className="ghost-btn" disabled={busy !== null} onClick={() => download('pdf')}>
          {busy === 'pdf' ? 'Preparing…' : 'Download PDF'}
        </button>
      </div>
    </div>
  )

  const shell = (body) => (
    <section className="panel">
      <h2>🧾 Report</h2>
      {controls}
      {downloadError && <p className="subtitle" role="alert">{downloadError}</p>}
      {body}
    </section>
  )

  if (error && !data) return shell(<p className="subtitle">Couldn’t load the report: {error}</p>)
  if (!data || !data.totals || !Array.isArray(data.categories) || !Array.isArray(data.periods)) return shell(<p className="subtitle">Loading…</p>)

  const t = data.totals
  const rows = chartCategories(data.categories)
  const periodRows = periodChartRows(data.periods)
  const daily = data.kind === 'month'

  return (
    <>
      {shell(
        <>
          <h3 data-testid="report-title">{data.label}</h3>
          <p data-testid="report-summary">{summaryText(data)}</p>
          {data.unconverted_count > 0 && (
            <p className="subtitle">
              {data.unconverted_count} {data.unconverted_count === 1 ? 'expense is' : 'expenses are'} left out because its currency has no exchange rate.
            </p>
          )}
        </>,
      )}

      <section className="cards">
        <div className="card">
          <span className="card-label">Spent</span>
          <span className="card-value card-value--money">{money(t.spent)}</span>
          <span className={`report-sub ${changeDirection(data)}`} data-testid="report-change">{changeText(data)}</span>
        </div>
        <div className="card">
          <span className="card-label">Income</span>
          <span className="card-value card-value--money">{money(t.income)}</span>
          <span className="report-sub">
            Net {money(t.net)}
            {t.savings_rate_pct != null && ` · saved ${t.savings_rate_pct}%`}
          </span>
        </div>
        <div className="card">
          <span className="card-label">Average per day</span>
          <span className="card-value card-value--money">{money(t.avg_per_day)}</span>
          {t.avg_per_month != null && <span className="report-sub">{money(t.avg_per_month)} per month</span>}
        </div>
      </section>

      {data.categories.length > 0 && (
        <section className="panel">
          <h2>🍰 Spending by category</h2>
          <div data-testid="report-category-chart" role="img" aria-label={describeCategoryChart(rows)}>
            <ResponsiveContainer width="100%" height={categoryChartHeight(rows)}>
              <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 90, left: 0, bottom: 4 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="name" width={110} tickLine={false} {...axis} />
                <Tooltip content={<AmountTip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="total" isAnimationActive={false} radius={[0, 4, 4, 0]}>
                  {rows.map((r) => (
                    <Cell key={r.name} fill={r.other ? MUTED : ACCENT} />
                  ))}
                  <LabelList dataKey="total" position="right" formatter={(v) => money(v)} fontSize={12} fill="#5c6577" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Category</th>
                <th className="right">Amount</th>
                <th className="right">Share</th>
                <th className="right">Expenses</th>
              </tr>
            </thead>
            <tbody>
              {data.categories.map((c) => (
                <tr key={c.category}>
                  <td>{c.category}</td>
                  <td className="right">{money(c.total)}</td>
                  <td className="right">{c.share_pct}%</td>
                  <td className="right">{c.count}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th>Total</th>
                <th className="right">{money(t.spent)}</th>
                <th />
                <th className="right">{t.count}</th>
              </tr>
            </tfoot>
          </table>
        </section>
      )}

      {data.categories.length > 0 && (
        <section className="panel">
          <h2>{daily ? '📅 Spending by day' : '📅 Spending by month'}</h2>
          <div data-testid="report-period-chart" role="img" aria-label={describePeriodChart(data)}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={periodRows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
                <XAxis dataKey="name" interval={daily ? (phone ? 4 : 1) : 0} tickFormatter={(v) => tickLabel(v, daily, phone)} {...axis} />
                <YAxis {...axis} width={52} />
                <Tooltip content={<AmountTip />} cursor={{ fill: 'rgba(0,0,0,0.04)' }} />
                <Bar dataKey="total" fill={ACCENT} isAnimationActive={false} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {data.top_shops.length > 0 && (
        <section className="panel">
          <h2>🏪 Top shops</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Shop</th>
                <th className="right">Amount</th>
                <th className="right">Share</th>
                <th className="right">Expenses</th>
              </tr>
            </thead>
            <tbody>
              {data.top_shops.map((s) => (
                <tr key={s.shop}>
                  <td>{s.shop}</td>
                  <td className="right">{money(s.total)}</td>
                  <td className="right">{s.share_pct}%</td>
                  <td className="right">{s.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {data.largest.length > 0 && (
        <section className="panel">
          <h2>💎 Largest expenses</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Item</th>
                <th>Category</th>
                <th className="right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {data.largest.map((x, i) => (
                <tr key={`${x.date}|${x.description}|${x.amount}|${i}`}>
                  <td>{x.date}</td>
                  <td>
                    {x.description || x.category}
                    {x.shop && <span className="report-sub">{x.shop}</span>}
                  </td>
                  <td>{x.category}</td>
                  <td className="right">{money(x.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </>
  )
}

import { useEffect, useRef, useState } from 'react'
import { fetchExpenses, fetchIncome } from '../api/client.js'
import { money } from '../format.js'
import {
  monthRange, shiftMonth, monthTitle, currentMonthKey, incomeInMonth, totalsByCurrency, includesIncome, scopeFilters,
} from '../monthDetail.js'

const PAGE_SIZE = 200
const MAX_PAGES = 10

async function loadMonthExpenses(month, scope, spaceIds) {
  const { from, to } = monthRange(month)
  const items = []
  let total = 0
  for (let page = 1; page <= MAX_PAGES; page++) {
    const res = await fetchExpenses({ ...scopeFilters(scope, spaceIds), date_from: from, date_to: to, page, page_size: PAGE_SIZE })
    items.push(...res.items)
    total = res.total
    if (res.items.length === 0 || items.length >= total) break
  }
  return { items, total }
}

function Totals({ rows }) {
  const totals = totalsByCurrency(rows)
  if (totals.length === 0) return null
  return (
    <strong data-testid="month-total">
      {totals.map((t, i) => (
        <span key={t.currency}>
          {i > 0 && ' + '}
          {money(t.total, t.currency)}
        </span>
      ))}
    </strong>
  )
}

// Every expense and every income entry of one month, opened by clicking that month on a chart.
export default function MonthDetailDialog({ month, scope, spaceIds, onClose, onChangeMonth }) {
  const [state, setState] = useState({ loading: true, error: null, expenses: [], expenseTotal: 0, income: [] })
  const latest = useRef(0)
  const closeRef = useRef(null)
  const showIncome = includesIncome(scope, spaceIds)
  const idsKey = (spaceIds || []).join(',')

  useEffect(() => {
    const request = ++latest.current
    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.all([
      loadMonthExpenses(month, scope, spaceIds),
      showIncome ? fetchIncome() : Promise.resolve([]),
    ])
      .then(([exp, inc]) => {
        if (request !== latest.current) return
        setState({
          loading: false, error: null, expenses: exp.items, expenseTotal: exp.total, income: incomeInMonth(inc, month),
        })
      })
      .catch((err) => {
        if (request === latest.current) setState((s) => ({ ...s, loading: false, error: err.message || 'Could not load this month.' }))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, scope, idsKey, showIncome])

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const { loading, error, expenses, expenseTotal, income } = state
  const canGoNext = shiftMonth(month, 1) <= currentMonthKey()

  return (
    <div className="month-detail-backdrop" onClick={onClose}>
      <div
        className="month-detail"
        role="dialog"
        aria-modal="true"
        aria-label={`Expenses and income for ${monthTitle(month)}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="month-detail-head">
          <button type="button" aria-label="Previous month" onClick={() => onChangeMonth(shiftMonth(month, -1))}>‹</button>
          <h2>{monthTitle(month)}</h2>
          <button type="button" aria-label="Next month" disabled={!canGoNext} onClick={() => onChangeMonth(shiftMonth(month, 1))}>›</button>
          <button type="button" ref={closeRef} className="month-detail-close" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        {loading && <p className="subtitle">Loading…</p>}
        {error && <p className="subtitle" role="alert">Couldn’t load this month: {error}</p>}

        {!loading && !error && (
          <>
            <h3>
              Expenses ({expenseTotal}) <Totals rows={expenses} />
            </h3>
            {expenses.length === 0 ? (
              <p className="subtitle">No expenses this month.</p>
            ) : (
              <div className="month-detail-scroll">
                <table className="table" data-testid="month-expenses">
                  <thead>
                    <tr><th>Date</th><th>Description</th><th>Shop</th><th>Category</th><th className="num">Amount</th></tr>
                  </thead>
                  <tbody>
                    {expenses.map((e) => (
                      <tr key={e.id}>
                        <td>{e.date}</td>
                        <td>{e.description}</td>
                        <td>{e.shop}</td>
                        <td>{e.category}</td>
                        <td className="num">{money(e.amount, e.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {expenseTotal > expenses.length && (
              <p className="subtitle">Showing the latest {expenses.length} of {expenseTotal} expenses. Use Spending to see them all.</p>
            )}

            {showIncome ? (
              <>
                <h3>
                  Income ({income.length}) <Totals rows={income} />
                </h3>
                {income.length === 0 ? (
                  <p className="subtitle">No income this month.</p>
                ) : (
                  <div className="month-detail-scroll">
                    <table className="table" data-testid="month-income">
                      <thead>
                        <tr><th>Date</th><th>Source</th><th>Note</th><th className="num">Amount</th></tr>
                      </thead>
                      <tbody>
                        {income.map((r) => (
                          <tr key={r.id}>
                            <td>{r.date}</td>
                            <td>{r.source}</td>
                            <td>{r.note}</td>
                            <td className="num">{money(r.amount, r.currency)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <p className="subtitle">Income is personal, so it isn’t shown for a shared space.</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

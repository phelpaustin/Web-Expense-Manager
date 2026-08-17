import { STATUS_COLORS } from '../constants.js'

export default function DashboardPage({
  summary,
  incomeSummary,
  budgets,
  trends,
  categories,
  onSetBudget,
  onDeleteBudget,
}) {
  return (
    <>
      <h1 className="page-title">📊 Dashboard</h1>

      {summary && (
        <section className="cards">
          <div className="card">
            <span className="card-label">Total spent</span>
            <span className="card-value">${summary.total.toFixed(2)}</span>
          </div>
          <div className="card">
            <span className="card-label">Transactions</span>
            <span className="card-value">{summary.count}</span>
          </div>
          <div className="card">
            <span className="card-label">Categories</span>
            <span className="card-value">{Object.keys(summary.by_category).length}</span>
          </div>
          {incomeSummary && (
            <div className="card">
              <span className="card-label">Net this month</span>
              <span className="card-value">
                ${(incomeSummary.this_month - summary.total).toFixed(2)}
              </span>
            </div>
          )}
        </section>
      )}

      {budgets.length > 0 && (
        <section className="panel">
          <h2>🎯 Budget status</h2>
          {budgets.map((b) => {
            const key = b.category === 'Total' ? '__total_monthly__' : b.category
            return (
              <div key={b.category} className={b.category === 'Total' ? 'budget-row total' : 'budget-row'}>
                <span className="budget-name">{b.category}</span>
                <div className="cat-bar-track">
                  <div
                    className="cat-bar-fill"
                    style={{
                      width: `${Math.min(b.pct, 100)}%`,
                      background: STATUS_COLORS[b.status] || '#64748b',
                    }}
                  />
                </div>
                <span className="budget-pct" style={{ color: STATUS_COLORS[b.status] }}>
                  {b.pct}%
                </span>
                <span className="budget-amt">${b.spent.toFixed(2)} spent</span>
                <input
                  className="budget-input"
                  type="number"
                  step="1"
                  min="1"
                  defaultValue={b.budget}
                  title="Budget amount — edit and press Enter"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') e.currentTarget.blur()
                  }}
                  onBlur={(e) => {
                    const v = parseFloat(e.target.value)
                    if (v && v !== b.budget) onSetBudget(key, v)
                  }}
                />
                <button className="delete-btn" onClick={() => onDeleteBudget(key)} title="Delete budget">
                  ✕
                </button>
              </div>
            )
          })}
        </section>
      )}

      {trends && (
        <section className="panel">
          <h2>📈 Trends</h2>
          <div className="trend-row">
            {trends.monthly.map((m) => (
              <div key={m.month} className="trend-cell">
                <span className="card-label">{m.month}</span>
                <span className="trend-value">${m.total.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div className="trend-meta">
            {trends.change && (
              <span>
                vs previous month:{' '}
                <strong className={trends.change.direction === 'up' ? 'up' : 'down'}>
                  {trends.change.direction === 'up' ? '▲' : '▼'} {Math.abs(trends.change.pct_change)}%
                </strong>
              </span>
            )}
            {trends.forecast_next_month != null && (
              <span>
                forecast next month: <strong>${trends.forecast_next_month.toFixed(2)}</strong>
              </span>
            )}
          </div>
        </section>
      )}

      {categories.length > 0 && (
        <section className="panel">
          <h2>🏆 Category breakdown</h2>
          {categories.map((c) => (
            <div key={c.category} className="cat-row">
              <span className="cat-name">{c.category}</span>
              <div className="cat-bar-track">
                <div className="cat-bar-fill" style={{ width: `${c.pct_of_total}%` }} />
              </div>
              <span className="cat-pct">{c.pct_of_total}%</span>
              <span className="cat-amt">${c.total.toFixed(2)}</span>
            </div>
          ))}
        </section>
      )}
    </>
  )
}

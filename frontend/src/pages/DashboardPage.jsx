import { useState } from 'react'
import { STATUS_COLORS } from '../constants.js'
import { money } from '../format.js'
import { SpendingTrendChart, CashFlowChart, CategoryDonut } from '../components/Charts.jsx'

const CHOOSE_SPACES = '__choose__'

export default function DashboardPage({
  summary,
  incomeSummary,
  budgets,
  trends,
  categories,
  onSetBudget,
  onDeleteBudget,
  metrics,
  periodStatus,
  budgetConfig,
  onSetBudgetConfig,
  groups,
  dashboardScope,
  onSetDashboardScope,
  dashboardSpaceIds,
  onSetDashboardSpaceIds,
}) {
  const [choosingSpaces, setChoosingSpaces] = useState(false)
  const [pendingSelection, setPendingSelection] = useState(dashboardSpaceIds || [])
  const multiActive = dashboardSpaceIds && dashboardSpaceIds.length > 0

  function spaceLabel(id) {
    if (id === 'personal') return 'Personal expenses'
    return groups.find((g) => String(g.id) === String(id))?.name || id
  }

  function handleSelectChange(value) {
    if (value === CHOOSE_SPACES) {
      setPendingSelection(dashboardSpaceIds && dashboardSpaceIds.length ? dashboardSpaceIds : ['personal'])
      setChoosingSpaces(true)
      return
    }
    setChoosingSpaces(false)
    onSetDashboardScope(value)
  }

  function toggleSpace(id) {
    setPendingSelection((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]))
  }

  function applySelection() {
    onSetDashboardSpaceIds(pendingSelection)
    setChoosingSpaces(false)
  }

  return (
    <>
      <div className="dashboard-header">
        <h1 className="page-title">📊 Dashboard</h1>
        {groups && groups.length > 0 && (
          <div className="scope-picker">
            <select
              className="scope-select"
              value={multiActive ? CHOOSE_SPACES : dashboardScope}
              onChange={(e) => handleSelectChange(e.target.value)}
              title="Show data for personal expenses only, one Expense Space, or a combined view"
            >
              <option value="all">All expenses</option>
              <option value="personal">Personal expenses</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
              <option value={CHOOSE_SPACES}>Choose spaces…</option>
            </select>
            {multiActive && !choosingSpaces && (
              <span className="subtitle">Selected spaces: {dashboardSpaceIds.map(spaceLabel).join(', ')}</span>
            )}
          </div>
        )}
      </div>

      {choosingSpaces && (
        <section className="panel">
          <h2>🗂️ Choose Expense Spaces</h2>
          <p className="subtitle">Combine two or more spaces into one view.</p>
          <ul className="space-checklist">
            <li>
              <label>
                <input
                  type="checkbox"
                  checked={pendingSelection.includes('personal')}
                  onChange={() => toggleSpace('personal')}
                />
                Personal expenses
              </label>
            </li>
            {groups.map((g) => (
              <li key={g.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={pendingSelection.includes(String(g.id))}
                    onChange={() => toggleSpace(String(g.id))}
                  />
                  {g.name}
                </label>
              </li>
            ))}
          </ul>
          <div className="auto-cat-row">
            <button type="button" onClick={applySelection} disabled={pendingSelection.length === 0}>
              Apply
            </button>
            <button type="button" className="ghost-btn" onClick={() => setChoosingSpaces(false)}>
              Cancel
            </button>
          </div>
        </section>
      )}

      {summary && (
        <section className="cards">
          <div className="card">
            <span className="card-label">Total spent</span>
            <span className="card-value">{money(summary.total)}</span>
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
                {money(incomeSummary.this_month - summary.total)}
              </span>
            </div>
          )}
        </section>
      )}

      {metrics && (
        <section className="cards">
          <div className="card">
            <span className="card-label">Savings rate</span>
            <span className="card-value">{metrics.savings_rate}%</span>
          </div>
          <div className="card">
            <span className="card-label">Monthly savings</span>
            <span className="card-value">{money(metrics.monthly_savings)}</span>
          </div>
          <div className="card">
            <span className="card-label">Projected spend</span>
            <span className="card-value">{money(metrics.monthly_projection)}</span>
          </div>
          <div className="card">
            <span className="card-label">Spend volatility</span>
            <span className="card-value">{metrics.volatility_cv}%</span>
          </div>
        </section>
      )}

      {periodStatus && (
        <section className="panel">
          <div className="period-header">
            <h2>🎯 {periodStatus.label} budget</h2>
            <div className="period-controls">
              <select
                value={budgetConfig.period}
                onChange={(e) => onSetBudgetConfig(e.target.value, budgetConfig.rollover)}
              >
                {['Weekly', 'Monthly', 'Annual'].map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={budgetConfig.rollover}
                  onChange={(e) => onSetBudgetConfig(budgetConfig.period, e.target.checked)}
                />
                Rollover
              </label>
            </div>
          </div>
          <div className="period-value">
            {money(periodStatus.spent)}{' '}
            <span className="period-of">/ {money(periodStatus.effective)}</span>
          </div>
          <div className="cat-bar-track" style={{ margin: '0.75rem 0 0.5rem' }}>
            <div
              className="cat-bar-fill"
              style={{
                width: `${Math.min(periodStatus.pct, 100)}%`,
                background: STATUS_COLORS[periodStatus.status] || '#64748b',
              }}
            />
          </div>
          <div className="trend-meta">
            <span>
              <strong style={{ color: STATUS_COLORS[periodStatus.status] }}>{periodStatus.pct}%</strong> used
            </span>
            <span>{money(periodStatus.remaining)} remaining</span>
            {periodStatus.rollover !== 0 && <span>rollover: {money(periodStatus.rollover)}</span>}
            <span>projected: {money(periodStatus.projected)}</span>
            <span>{periodStatus.days_remaining} days left</span>
          </div>
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
                <span className="budget-amt">{money(b.spent)} spent</span>
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
          <h2>📈 Spending trend</h2>
          <SpendingTrendChart data={trends.monthly} />
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
                forecast next month: <strong>{money(trends.forecast_next_month)}</strong>
              </span>
            )}
          </div>
        </section>
      )}

      {metrics && metrics.cash_flow && metrics.cash_flow.length > 0 && (
        <section className="panel">
          <h2>💸 Cash flow</h2>
          <CashFlowChart data={metrics.cash_flow} />
        </section>
      )}

      {categories.length > 0 && (
        <section className="panel">
          <h2>🏆 Category breakdown</h2>
          <CategoryDonut data={categories} />
        </section>
      )}
    </>
  )
}

import CurrencySelect from '../components/CurrencySelect.jsx'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { STATUS_COLORS } from '../constants.js'
import { money } from '../format.js'
import TrendMeta from '../components/TrendMeta.jsx'
import ScopePicker from '../components/ScopePicker.jsx'
import BudgetRiskPanel from '../components/BudgetRiskPanel.jsx'
import { SpendingTrendChart } from '../components/Charts.jsx'
import MonthDetailDialog from '../components/MonthDetailDialog.jsx'
const TOTAL_BUDGET_KEY = '__total_monthly__'

export default function DashboardPage({
  currencies = [],
  displayCurrency,
  summary,
  budgets,
  trends,
  onSetBudget,
  onDeleteBudget,
  metrics,
  periodStatus,
  budgetRisk,
  budgetConfig,
  onSetBudgetConfig,
  groups,
  trips,
  dashboardScope,
  onSetDashboardScope,
  dashboardSpaceIds,
  onSetDashboardSpaceIds,
}) {
  const [budgetFormOpen, setBudgetFormOpen] = useState(false)
  const [detailMonth, setDetailMonth] = useState(null)
  const [budgetType, setBudgetType] = useState('total')
  const [newBudgetCategory, setNewBudgetCategory] = useState('')
  const [newBudgetAmount, setNewBudgetAmount] = useState('')
  const [newBudgetCurrency, setNewBudgetCurrency] = useState('')
  const [savingBudget, setSavingBudget] = useState(false)
  const [budgetFormError, setBudgetFormError] = useState('')
  const hasTotalBudget = Boolean(periodStatus)
  const showBudgetForm = budgets.length === 0 || budgetFormOpen

  async function handleAddBudget(event) {
    event.preventDefault()
    setBudgetFormError('')

    const selectedBudgetType = hasTotalBudget ? 'category' : budgetType
    const category = selectedBudgetType === 'total' ? TOTAL_BUDGET_KEY : newBudgetCategory.trim()
    const amount = Number(newBudgetAmount)
    if (selectedBudgetType === 'category' && !category) {
      setBudgetFormError('Enter a category name.')
      return
    }
    if (selectedBudgetType === 'category' && category.toLowerCase() === 'total') {
      setBudgetFormError('“Total” is reserved for the overall budget.')
      return
    }
    if (selectedBudgetType === 'category' && budgets.some((budget) => budget.category.toLowerCase() === category.toLowerCase())) {
      setBudgetFormError('A budget already exists for that category. Edit its amount in the list above.')
      return
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setBudgetFormError('Enter an amount greater than zero.')
      return
    }

    setSavingBudget(true)
    try {
      const saved = await onSetBudget(category, amount, newBudgetCurrency)
      if (!saved) {
        setBudgetFormError('Could not save the budget. Please try again.')
        return
      }
      setNewBudgetCategory('')
      setNewBudgetAmount('')
      setNewBudgetCurrency('')
      setBudgetFormOpen(false)
    } catch {
      setBudgetFormError('Could not save the budget. Please try again.')
    } finally {
      setSavingBudget(false)
    }
  }

  return (
    <>
      <ScopePicker
        title="📊 Dashboard"
        groups={groups}
        trips={trips}
        dashboardScope={dashboardScope}
        onSetDashboardScope={onSetDashboardScope}
        dashboardSpaceIds={dashboardSpaceIds}
        onSetDashboardSpaceIds={onSetDashboardSpaceIds}
      />

      {summary && summary.unconverted_count > 0 && (
        <div className="auth-error" role="alert">
          {summary.unconverted_count} expense{summary.unconverted_count === 1 ? '' : 's'} in a currency without
          an exchange rate {summary.unconverted_count === 1 ? 'is' : 'are'} left out of these totals. Edit{' '}
          {summary.unconverted_count === 1 ? 'it' : 'them'} on the Spending page (All items) and choose a supported currency.
        </div>
      )}
      {(summary || metrics) && (
        <section className="cards">
          {summary && (
            <div className="card">
              <span className="card-label">Total spent</span>
              <span className="card-value">{money(summary.total)}</span>
            </div>
          )}
          {metrics && (
            <>
              <div className="card">
                <span className="card-label">Net this month</span>
                <span className="card-value card-value--money">{money(metrics.monthly_savings)}</span>
              </div>
              <div className="card">
                <span className="card-label">Savings rate</span>
                <span className="card-value">{metrics.savings_rate}%</span>
              </div>
              <div className="card">
                <span className="card-label">Projected spend</span>
                <span className="card-value">{money(metrics.monthly_projection)}</span>
              </div>
            </>
          )}
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
          <TrendMeta trends={trends} />
        </section>
      )}

      <section className="panel">
          <div className="budget-panel-header">
            <h2>🎯 Budget status</h2>
            {budgets.length > 0 && (
              <button
                type="button"
                className="ghost-btn"
                onClick={() => {
                  setBudgetFormError('')
                  setBudgetFormOpen((open) => !open)
                }}
                aria-expanded={showBudgetForm}
              >
                {showBudgetForm ? 'Cancel' : 'Add budget'}
              </button>
            )}
          </div>
          {budgets.length === 0 && (
            <p className="budget-setup-copy">Set an overall limit or create your first category budget.</p>
          )}
          {budgets.map((b) => {
            const isComputedTotal = b.category === 'Total' && !hasTotalBudget
            const key = b.category === 'Total' ? TOTAL_BUDGET_KEY : b.category
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
                {isComputedTotal ? (
                  <span className="budget-amt">{money(b.budget)} total</span>
                ) : (
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
                )}
                {!isComputedTotal && (
                  <button className="delete-btn" onClick={() => onDeleteBudget(key)} title="Delete budget">
                    ✕
                  </button>
                )}
              </div>
            )
          })}
          {showBudgetForm && (
            <form className="budget-create-form" onSubmit={handleAddBudget}>
              <label className="budget-create-field">
                Budget type
                <select
                  value={hasTotalBudget ? 'category' : budgetType}
                  onChange={(event) => {
                    setBudgetType(event.target.value)
                    setBudgetFormError('')
                  }}
                >
                  {!hasTotalBudget && <option value="total">Overall budget</option>}
                  <option value="category">Category budget</option>
                </select>
              </label>
              {(hasTotalBudget || budgetType === 'category') && (
                <label className="budget-create-field">
                  Category
                  <input
                    type="text"
                    value={newBudgetCategory}
                    onChange={(event) => setNewBudgetCategory(event.target.value)}
                    placeholder="e.g. Groceries"
                    maxLength={100}
                    required
                  />
                </label>
              )}
              <label className="budget-create-field">
                Budget amount
                <input
                  type="number"
                  value={newBudgetAmount}
                  onChange={(event) => setNewBudgetAmount(event.target.value)}
                  min="0.01"
                  step="0.01"
                  placeholder="0.00"
                  required
                />
                <CurrencySelect
                  value={newBudgetCurrency}
                  onChange={setNewBudgetCurrency}
                  currencies={currencies}
                  defaultCurrency={displayCurrency}
                  title="Currency of this budget"
                />
              </label>
              <button type="submit" disabled={savingBudget}>
                {savingBudget ? 'Saving…' : 'Save budget'}
              </button>
              {budgetFormError && <p className="budget-form-error" role="alert">{budgetFormError}</p>}
            </form>
          )}
      </section>

      <BudgetRiskPanel risk={budgetRisk} />

      {trends && (
        <section className="panel">
          <div className="period-header">
            <h2>📈 Spending trend</h2>
            <Link to="/insights">More in Insights</Link>
          </div>
          <SpendingTrendChart data={trends.monthly} onSelectMonth={setDetailMonth} />
          <p className="chart-hint">Click a month to see its expenses and income.</p>
          <div className="trend-meta">
            {trends.change && (
              <span>
                vs previous month:{' '}
                <strong className={trends.change.direction === 'up' ? 'up' : 'down'}>
                  {trends.change.direction === 'up' ? '▲' : '▼'} {Math.abs(trends.change.pct_change)}%
                </strong>
              </span>
            )}
          </div>
        </section>
      )}

      {detailMonth && (
        <MonthDetailDialog
          month={detailMonth}
          scope={dashboardScope}
          spaceIds={dashboardSpaceIds}
          onChangeMonth={setDetailMonth}
          onClose={() => setDetailMonth(null)}
        />
      )}
    </>
  )
}

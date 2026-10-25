import { useState } from 'react'
import { CategoryDonut } from './Charts.jsx'
import {
  PERIOD_PRESETS, PICK_MONTH, PICK_YEAR, availablePeriods, categoryTotals, monthLabel,
} from '../categoryPeriod.js'

// Where the money went, as a donut, for all time, a recent period, or a month or year you choose.
export default function CategoryBreakdown({ categories, categoryMonths = [] }) {
  // 'all' keeps the card's original behaviour until the user changes it.
  const [catPeriod, setCatPeriod] = useState('all')
  const [catValue, setCatValue] = useState('')
  const catAvailable = availablePeriods(categoryMonths)
  // Fall back to the all-time totals if the per-month rows aren't there (e.g. an older server).
  const catData = categoryMonths.length ? categoryTotals(categoryMonths, catPeriod, catValue) : categories

  if (!categories || categories.length === 0) return null

  return (
    <section className="panel">
      <div className="period-header">
        <h2>🏆 Category breakdown</h2>
        <div className="period-controls" data-testid="category-period">
          <select
            aria-label="Category breakdown period"
            value={catPeriod}
            onChange={(e) => {
              const next = e.target.value
              setCatPeriod(next)
              // Preselect the newest month or year that has data when switching to a picker.
              if (next === PICK_MONTH) setCatValue(catAvailable.months[0] || '')
              if (next === PICK_YEAR) setCatValue(catAvailable.years[0] || '')
            }}
          >
            {PERIOD_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
            <option value={PICK_MONTH}>Choose a month…</option>
            <option value={PICK_YEAR}>Choose a year…</option>
          </select>
          {catPeriod === PICK_MONTH && (
            <select aria-label="Month" value={catValue} onChange={(e) => setCatValue(e.target.value)}>
              {catAvailable.months.map((k) => (
                <option key={k} value={k}>
                  {monthLabel(k)}
                </option>
              ))}
            </select>
          )}
          {catPeriod === PICK_YEAR && (
            <select aria-label="Year" value={catValue} onChange={(e) => setCatValue(e.target.value)}>
              {catAvailable.years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>
      {catData.length > 0 ? (
        <CategoryDonut data={catData} />
      ) : (
        <p className="subtitle">No spending in this period.</p>
      )}
    </section>
  )
}

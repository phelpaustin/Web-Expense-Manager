import { describe, it, expect } from 'vitest'
import { availablePeriods, categoryTotals, monthLabel, periodRange, PICK_MONTH, PICK_YEAR } from '../categoryPeriod.js'

// "Today" is 15 Mar 2026 throughout.
const TODAY = new Date(2026, 2, 15)

const ROWS = [
  { month: '2025-03', category: 'Rent', total: '100.00' },
  { month: '2025-12', category: 'Rent', total: '200.00' },
  { month: '2025-12', category: 'Groceries', total: '50.00' },
  { month: '2026-01', category: 'Rent', total: '300.00' },
  { month: '2026-02', category: 'Groceries', total: '40.50' },
  { month: '2026-03', category: 'Groceries', total: '10.25' },
  { month: '2026-03', category: 'Meat', total: '5.00' },
]

describe('periodRange', () => {
  it('covers the presets relative to today', () => {
    expect(periodRange('this_month', '', TODAY)).toEqual(['2026-03', '2026-03'])
    expect(periodRange('last_month', '', TODAY)).toEqual(['2026-02', '2026-02'])
    expect(periodRange('last_3', '', TODAY)).toEqual(['2026-01', '2026-03'])
    expect(periodRange('last_12', '', TODAY)).toEqual(['2025-04', '2026-03'])
    expect(periodRange('this_year', '', TODAY)).toEqual(['2026-01', '2026-12'])
    expect(periodRange('last_year', '', TODAY)).toEqual(['2025-01', '2025-12'])
    expect(periodRange('all', '', TODAY)).toBeNull()
  })

  it('last month rolls back across a year boundary', () => {
    expect(periodRange('last_month', '', new Date(2026, 0, 10))).toEqual(['2025-12', '2025-12'])
    expect(periodRange('last_3', '', new Date(2026, 0, 10))).toEqual(['2025-11', '2026-01'])
  })

  it('handles a picked month or year', () => {
    expect(periodRange(PICK_MONTH, '2025-12', TODAY)).toEqual(['2025-12', '2025-12'])
    expect(periodRange(PICK_YEAR, '2025', TODAY)).toEqual(['2025-01', '2025-12'])
  })
})

describe('categoryTotals', () => {
  it('sums every month for all time, biggest first', () => {
    const out = categoryTotals(ROWS, 'all', '', TODAY)
    expect(out.map((r) => [r.category, r.total])).toEqual([
      ['Rent', 600],
      ['Groceries', 100.75],
      ['Meat', 5],
    ])
  })

  it('limits to the period and works out each share of that period', () => {
    const out = categoryTotals(ROWS, 'this_month', '', TODAY)
    expect(out.map((r) => r.category)).toEqual(['Groceries', 'Meat'])
    expect(out[0].pct_of_total).toBeCloseTo(67.2, 1)
    expect(out[1].pct_of_total).toBeCloseTo(32.8, 1)
  })

  it('sums a whole year', () => {
    const out = categoryTotals(ROWS, 'last_year', '', TODAY)
    expect(out.map((r) => [r.category, r.total])).toEqual([
      ['Rent', 300],
      ['Groceries', 50],
    ])
  })

  it('is empty when nothing was spent in the period', () => {
    expect(categoryTotals(ROWS, PICK_MONTH, '2024-06', TODAY)).toEqual([])
    expect(categoryTotals([], 'all', '', TODAY)).toEqual([])
  })
})

describe('availablePeriods', () => {
  it('lists months and years that have spending, newest first', () => {
    const { months, years } = availablePeriods(ROWS)
    expect(months).toEqual(['2026-03', '2026-02', '2026-01', '2025-12', '2025-03'])
    expect(years).toEqual(['2026', '2025'])
  })
})

describe('monthLabel', () => {
  it('formats a month key', () => {
    expect(monthLabel('2026-03')).toBe('Mar 2026')
  })
})

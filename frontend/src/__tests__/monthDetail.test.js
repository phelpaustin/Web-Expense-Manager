import { describe, it, expect } from 'vitest'
import {
  isMonthKey, monthRange, shiftMonth, monthTitle, incomeInMonth, totalsByCurrency, includesIncome, scopeFilters,
} from '../monthDetail.js'

describe('monthDetail helpers', () => {
  it('validates month keys', () => {
    expect(isMonthKey('2025-01')).toBe(true)
    expect(isMonthKey('2025-13')).toBe(false)
    expect(isMonthKey('Nov')).toBe(false)
  })

  it('gives the first and last day of a month, leap years included', () => {
    expect(monthRange('2025-01')).toEqual({ from: '2025-01-01', to: '2025-01-31' })
    expect(monthRange('2024-02')).toEqual({ from: '2024-02-01', to: '2024-02-29' })
    expect(monthRange('2025-02').to).toBe('2025-02-28')
  })

  it('shifts across year boundaries', () => {
    expect(shiftMonth('2025-12', 1)).toBe('2026-01')
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
  })

  it('titles a month', () => {
    expect(monthTitle('2025-01')).toBe('January 2025')
  })

  it('keeps only the income of that month, newest first', () => {
    const rows = [
      { id: 1, date: '2025-01-05', amount: '10' },
      { id: 2, date: '2025-02-01', amount: '20' },
      { id: 3, date: '2025-01-25', amount: '30' },
    ]
    expect(incomeInMonth(rows, '2025-01').map((r) => r.id)).toEqual([3, 1])
  })

  it('totals per currency in whole cents', () => {
    const rows = [
      { currency: 'SEK', amount: '0.1' },
      { currency: 'SEK', amount: '0.2' },
      { currency: 'EUR', amount: '5.00' },
    ]
    expect(totalsByCurrency(rows)).toEqual([
      { currency: 'SEK', total: 0.3 },
      { currency: 'EUR', total: 5 },
    ])
  })

  it('shows income only for the personal view', () => {
    expect(includesIncome('all', [])).toBe(true)
    expect(includesIncome('personal', [])).toBe(true)
    expect(includesIncome('3', [])).toBe(false)
    expect(includesIncome('all', ['personal', '3'])).toBe(true)
    expect(includesIncome('all', ['3'])).toBe(false)
  })

  it('builds the same space filters the dashboard uses', () => {
    expect(scopeFilters('all', [])).toEqual({})
    expect(scopeFilters('personal', [])).toEqual({ scope: 'personal' })
    expect(scopeFilters('all', ['personal', '3'])).toEqual({ space_ids: 'personal,3' })
  })
})

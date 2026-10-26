import { describe, it, expect } from 'vitest'
import {
  isMonthKey, monthRange, shiftMonth, monthTitle, incomeInMonth, totalsByCurrency, includesIncome, scopeFilters,
  editFormFor, expenseChanges, canEditExpense,
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

  describe('editing an expense', () => {
    const expense = { id: 1, date: '2025-01-10', description: 'Milk', shop: 'ICA', category: 'Food', amount: '25.50', currency: 'SEK', group_id: null }

    it('builds the form from the expense', () => {
      expect(editFormFor(expense)).toEqual({
        date: '2025-01-10', description: 'Milk', shop: 'ICA', category: 'Food', amount: '25.50', currency: 'SEK',
      })
    })

    it('sends nothing when nothing changed', () => {
      expect(expenseChanges(expense, editFormFor(expense))).toEqual({ changes: {} })
    })

    it('sends only the fields that changed', () => {
      const form = { ...editFormFor(expense), shop: ' Coop ', amount: '30' }
      expect(expenseChanges(expense, form)).toEqual({ changes: { shop: 'Coop', amount: 30 } })
    })

    it('treats 25.5 and 25.50 as the same amount', () => {
      expect(expenseChanges(expense, { ...editFormFor(expense), amount: '25.5' })).toEqual({ changes: {} })
    })

    it('rejects input the server would refuse', () => {
      expect(expenseChanges(expense, { ...editFormFor(expense), amount: '0' }).error).toMatch(/amount/)
      expect(expenseChanges(expense, { ...editFormFor(expense), amount: 'abc' }).error).toMatch(/amount/)
      expect(expenseChanges(expense, { ...editFormFor(expense), category: ' ' }).error).toMatch(/category/)
      expect(expenseChanges(expense, { ...editFormFor(expense), date: '' }).error).toMatch(/date/)
    })

    it('blocks edits in a space where you are only a viewer', () => {
      const spaces = [{ id: 3, role: 'viewer' }, { id: 4, role: 'editor' }]
      expect(canEditExpense({ group_id: null }, spaces)).toBe(true)
      expect(canEditExpense({ group_id: 3 }, spaces)).toBe(false)
      expect(canEditExpense({ group_id: 4 }, spaces)).toBe(true)
      expect(canEditExpense({ group_id: 9 }, [])).toBe(true)
    })
  })
})

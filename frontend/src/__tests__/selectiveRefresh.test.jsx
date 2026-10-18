import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import * as client from '../api/client.js'
import { useAppData, PART, EXPENSE_PARTS } from '../hooks/useAppData.js'
import { useIncomeHandlers } from '../hooks/useIncomeHandlers.js'
import { useBudgetHandlers } from '../hooks/useBudgetHandlers.js'
import { useRecurringHandlers } from '../hooks/useRecurringHandlers.js'
import { useExpenseHandlers } from '../hooks/useExpenseHandlers.js'
import { useTripHandlers } from '../hooks/useTripHandlers.js'

const LOADERS = ['fetchDashboard', 'fetchIncome', 'fetchIncomeSummary', 'fetchRecurring', 'fetchOptions', 'fetchBudgetConfig', 'fetchTrips', 'fetchGroups']

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchDashboard.mockResolvedValue({ summary: null, trends: null, categories: [], budgets: [], metrics: null, period_status: null, alerts: [] })
  client.fetchOptions.mockResolvedValue({ categories: [], subcategories: {}, units: [], shops: [], base_currency: 'SEK', display_currency: 'SEK', currencies: [] })
  client.fetchIncomeSummary.mockResolvedValue(null)
  client.fetchBudgetConfig.mockResolvedValue({ period: 'Monthly', rollover: false })
})

const called = () => LOADERS.filter((n) => client[n].mock.calls.length > 0)

describe('loadAll(parts)', () => {
  it('refreshes everything when called without parts', async () => {
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.loadAll() })
    expect(called()).toEqual(LOADERS)
  })

  it('refreshes only the named parts', async () => {
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.loadAll([PART.INCOME]) })
    expect(called()).toEqual(['fetchIncome', 'fetchIncomeSummary'])
  })

  it('treats an empty list as "everything" rather than "nothing"', async () => {
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.loadAll([]) })
    expect(called()).toEqual(LOADERS)
  })

  it('EXPENSE_PARTS covers the dashboard, options, trips and groups but not income or recurring', async () => {
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.loadAll(EXPENSE_PARTS) })
    expect(called()).toEqual(['fetchDashboard', 'fetchOptions', 'fetchTrips', 'fetchGroups'])
  })

  it('keeps data from parts that were not refreshed', async () => {
    client.fetchIncome.mockResolvedValue([{ id: 1, amount: 5 }])
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.loadAll() })
    client.fetchIncome.mockResolvedValue([])
    await act(async () => { await result.current.loadAll(EXPENSE_PARTS) })
    expect(result.current.income).toEqual([{ id: 1, amount: 5 }])
  })
})

describe('handlers name what they changed', () => {
  it('income refreshes income and the dashboard', async () => {
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useIncomeHandlers(loadAll, vi.fn()))
    await act(async () => { await result.current.handleDeleteIncome(1) })
    expect(loadAll).toHaveBeenCalledWith([PART.INCOME, PART.DASHBOARD])
  })

  it('budgets refresh the dashboard and the budget settings', async () => {
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useBudgetHandlers(loadAll, vi.fn()))
    await act(async () => { await result.current.handleDeleteBudget('Food') })
    expect(loadAll).toHaveBeenCalledWith([PART.DASHBOARD, PART.BUDGET_CONFIG])
  })

  it('editing a recurring template refreshes only recurring; applying one also refreshes expense data', async () => {
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useRecurringHandlers(loadAll, vi.fn()))
    await act(async () => { await result.current.handleDeleteRecurring(1) })
    expect(loadAll).toHaveBeenLastCalledWith([PART.RECURRING])
    await act(async () => { await result.current.handleApplyRecurring(1) })
    expect(loadAll).toHaveBeenLastCalledWith([PART.RECURRING, ...EXPENSE_PARTS])
  })

  it('deleting an expense does not refresh income or recurring', async () => {
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useExpenseHandlers(loadAll, vi.fn()))
    await act(async () => { await result.current.handleDelete(1) })
    expect(loadAll).toHaveBeenCalledWith(EXPENSE_PARTS)
  })

  it('trip changes refresh expense data and spaces', async () => {
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useTripHandlers(loadAll, vi.fn()))
    await act(async () => { await result.current.handleDeleteTrip(1) })
    expect(loadAll).toHaveBeenCalledWith(EXPENSE_PARTS)
  })
})

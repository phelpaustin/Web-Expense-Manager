import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { useIncomeHandlers } from '../hooks/useIncomeHandlers.js'
import { useRecurringHandlers } from '../hooks/useRecurringHandlers.js'
import { useBillsHandlers } from '../hooks/useBillsHandlers.js'

beforeEach(() => vi.clearAllMocks())

describe('a missing or zero amount is stopped before it is sent', () => {
  it('for income', async () => {
    const setError = vi.fn()
    const { result } = renderHook(() => useIncomeHandlers(vi.fn(async () => {}), setError))
    await act(async () => { await result.current.handleAddIncome({ preventDefault() {} }) })
    expect(setError).toHaveBeenCalledWith('Enter an amount greater than zero')
    expect(client.createIncome).not.toHaveBeenCalled()
  })

  it('for a recurring payment', async () => {
    const setError = vi.fn()
    const { result } = renderHook(() => useRecurringHandlers(vi.fn(async () => {}), setError))
    await act(async () => { await result.current.handleAddRecurring({ preventDefault() {} }) })
    expect(setError).toHaveBeenCalledWith('Enter an amount greater than zero')
    expect(client.createRecurring).not.toHaveBeenCalled()
  })
})

describe('bills when the user signs out', () => {
  it('forgets the list, so the next person does not see it', async () => {
    client.fetchBills.mockResolvedValue({ items: [{ id: 1, shop: 'ICA', amount: 5, currency: 'SEK', status: 'pending', date: '2026-07-21' }], total: 1, page: 1, page_size: 25, counts: { pending: 1, total_only: 0, itemised: 0, all: 1 } })
    const { result, rerender } = renderHook(({ on }) => useBillsHandlers(vi.fn(async () => {}), vi.fn(), vi.fn(), on), { initialProps: { on: true } })
    await waitFor(() => expect(result.current.data.items).toHaveLength(1))
    rerender({ on: false })
    await waitFor(() => expect(result.current.data.items).toHaveLength(0))
  })
})

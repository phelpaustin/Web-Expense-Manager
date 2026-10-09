import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { useExpenseHandlers, positiveAmount } from '../hooks/useExpenseHandlers.js'

describe('positiveAmount', () => {
  it.each([
    ['12.5', 12.5], ['  7 ', 7], [3, 3], ['0.01', 0.01],
  ])('accepts %s', (input, expected) => expect(positiveAmount(input)).toBe(expected))

  it.each([['', 0], ['abc', 0], ['0', 0], ['-5', 0], [NaN, 0], [undefined, 0], ['Infinity', 0]])(
    'rejects %j',
    (input) => expect(positiveAmount(input)).toBeNull(),
  )
})

describe('expense form handlers never send an invalid amount', () => {
  let loadAll, setError
  beforeEach(() => {
    loadAll = vi.fn(async () => {})
    setError = vi.fn()
  })

  it('saveEdit with a cleared amount shows a message and does not call the API', async () => {
    const { result } = renderHook(() => useExpenseHandlers(loadAll, setError))
    act(() => result.current.startEdit({ id: 5, date: '2026-10-01', category: 'Food', amount: '', currency: 'SEK' }))
    await act(async () => { await result.current.saveEdit(5) })
    expect(setError).toHaveBeenCalledWith('Enter an amount greater than zero')
    expect(client.updateExpense).not.toHaveBeenCalled()
  })

  it('saveEdit sends a real number, and leaves currency out when unchanged-empty', async () => {
    const { result } = renderHook(() => useExpenseHandlers(loadAll, setError))
    act(() => result.current.startEdit({ id: 5, date: '2026-10-01', category: 'Food', amount: '12.5', currency: '' }))
    await act(async () => { await result.current.saveEdit(5) })
    const [id, payload] = client.updateExpense.mock.calls[0]
    expect(id).toBe(5)
    expect(payload.amount).toBe(12.5)
    expect(payload.currency).toBeUndefined()
    expect(loadAll).toHaveBeenCalled()
  })

  it('handleAdd rejects a zero or empty amount before calling the API', async () => {
    const { result } = renderHook(() => useExpenseHandlers(loadAll, setError))
    for (const bad of ['', '0', 'abc']) {
      act(() => result.current.setForm({ ...result.current.form, amount: bad, date: '2026-10-01', category: 'Food' }))
      await act(async () => { await result.current.handleAdd({ preventDefault() {} }) })
    }
    expect(client.createExpense).not.toHaveBeenCalled()
    expect(setError).toHaveBeenCalledTimes(3)
  })

  it('handleAdd sends the amount as a number and omits an unset currency (server picks the default)', async () => {
    const { result } = renderHook(() => useExpenseHandlers(loadAll, setError))
    act(() => result.current.setForm({ ...result.current.form, amount: '40', date: '2026-10-01', category: 'Food' }))
    await act(async () => { await result.current.handleAdd({ preventDefault() {} }) })
    const payload = client.createExpense.mock.calls[0][0]
    expect(payload.amount).toBe(40)
    expect(payload.currency).toBeUndefined()
  })
})

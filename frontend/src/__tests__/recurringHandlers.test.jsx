import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { useRecurringHandlers } from '../hooks/useRecurringHandlers.js'

// Lets a test hold a request open and release it later.
function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

beforeEach(() => vi.clearAllMocks())

describe('useRecurringHandlers: applying', () => {
  it('ignores a second click on the same item while the first apply is still running', async () => {
    const gate = deferred()
    client.applyRecurring.mockImplementation(() => gate.promise)
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useRecurringHandlers(loadAll, vi.fn()))

    let first, second
    act(() => {
      first = result.current.handleApplyRecurring(7)
      second = result.current.handleApplyRecurring(7) // double click
    })
    await act(async () => {
      gate.resolve({})
      await Promise.all([first, second])
    })

    expect(client.applyRecurring).toHaveBeenCalledTimes(1)
    expect(loadAll).toHaveBeenCalledTimes(1)
  })

  it('does not block a different item, and allows applying again once the first has finished', async () => {
    const { result } = renderHook(() => useRecurringHandlers(vi.fn(async () => {}), vi.fn()))

    await act(async () => {
      await Promise.all([result.current.handleApplyRecurring(1), result.current.handleApplyRecurring(2)])
    })
    expect(client.applyRecurring).toHaveBeenCalledTimes(2)

    await act(async () => {
      await result.current.handleApplyRecurring(1)
    })
    expect(client.applyRecurring).toHaveBeenCalledTimes(3)
  })

  it('ignores a second "Apply all due" click while one is running', async () => {
    const gate = deferred()
    client.applyDueRecurring.mockImplementation(() => gate.promise)
    const { result } = renderHook(() => useRecurringHandlers(vi.fn(async () => {}), vi.fn()))

    let a, b
    act(() => {
      a = result.current.handleApplyDue()
      b = result.current.handleApplyDue()
    })
    await act(async () => {
      gate.resolve({})
      await Promise.all([a, b])
    })

    expect(client.applyDueRecurring).toHaveBeenCalledTimes(1)
  })

  it('reports a failed apply and unblocks the item so it can be retried', async () => {
    client.applyRecurring.mockRejectedValueOnce(new Error('This recurring item was just applied by another request.'))
    const setError = vi.fn()
    const { result } = renderHook(() => useRecurringHandlers(vi.fn(async () => {}), setError))

    await act(async () => {
      await result.current.handleApplyRecurring(3)
    })
    expect(setError).toHaveBeenCalledWith('This recurring item was just applied by another request.')

    await act(async () => {
      await result.current.handleApplyRecurring(3)
    })
    expect(client.applyRecurring).toHaveBeenCalledTimes(2)
  })
})

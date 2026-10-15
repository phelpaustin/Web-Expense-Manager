import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import * as client from '../api/client.js'
import { useAppData } from '../hooks/useAppData.js'

const OPTIONS = { categories: [], subcategories: {}, units: [], shops: [], base_currency: 'SEK', display_currency: 'SEK', currencies: [] }

beforeEach(() => {
  client.fetchOptions.mockImplementation(async () => ({ ...OPTIONS }))
  for (const name of ['fetchSummary', 'fetchTrends', 'fetchMetrics', 'fetchPeriodStatus', 'fetchIncomeSummary']) {
    client[name].mockImplementation(async () => null)
  }
  client.fetchBudgetConfig.mockImplementation(async () => ({ period: 'Monthly', rollover: false }))
})

describe('useAppData.resetData', () => {
  it('clears alerts, trips, groups and the dashboard scope along with the rest', async () => {
    client.fetchAlerts.mockImplementation(async () => [{ id: 1 }])
    client.fetchTrips.mockImplementation(async () => [{ id: 2 }])
    client.fetchGroups.mockImplementation(async () => [{ id: 3 }])
    const { result } = renderHook(() => useAppData())

    await act(async () => {
      await result.current.loadAll()
    })
    await act(async () => {
      await result.current.handleSetDashboardScope('7')
    })
    expect(result.current.alerts).toEqual([{ id: 1 }])
    expect(result.current.trips).toEqual([{ id: 2 }])
    expect(result.current.groups).toEqual([{ id: 3 }])
    expect(result.current.dashboardScope).toBe('7')

    act(() => result.current.setError('old error'))
    act(() => result.current.resetData())

    expect(result.current.alerts).toEqual([])
    expect(result.current.trips).toEqual([])
    expect(result.current.groups).toEqual([])
    expect(result.current.dashboardScope).toBe('all')
    expect(result.current.dashboardSpaceIds).toEqual([])
    expect(result.current.error).toBeNull()
  })

  it('discards results of a load that was still in flight when the user logged out', async () => {
    let release
    client.fetchTrips.mockImplementation(() => new Promise((resolve) => { release = () => resolve([{ id: 99, name: 'previous user trip' }]) }))
    client.fetchGroups.mockImplementation(async () => [{ id: 98 }])
    const { result } = renderHook(() => useAppData())

    let pending
    act(() => {
      pending = result.current.loadAll()
    })
    act(() => result.current.resetData()) // logout while the request is still running
    await act(async () => {
      release()
      await pending
    })

    expect(result.current.trips).toEqual([])
    expect(result.current.groups).toEqual([])
  })

  it('still applies a load that started after the reset (the next user)', async () => {
    client.fetchTrips.mockImplementation(async () => [{ id: 5 }])
    const { result } = renderHook(() => useAppData())

    act(() => result.current.resetData())
    await act(async () => {
      await result.current.loadAll()
    })

    await waitFor(() => expect(result.current.trips).toEqual([{ id: 5 }]))
  })
})

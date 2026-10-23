import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchSpendingMix } from '../api/client.js'

afterEach(() => vi.restoreAllMocks())

describe('fetchSpendingMix', () => {
  it('asks for 12 months by default and passes the months and the dashboard scope', async () => {
    const urls = []
    global.fetch = vi.fn(async (url) => {
      urls.push(String(url).replace(/^.*\/api/, '/api'))
      return { ok: true, status: 200, json: async () => ({}) }
    })

    await fetchSpendingMix()
    await fetchSpendingMix({ months: 3, scope: 'personal' })
    await fetchSpendingMix({ months: 6, spaceIds: ['personal', 7] })

    expect(urls).toEqual([
      '/api/analytics/spending-mix?months=12',
      '/api/analytics/spending-mix?scope=personal&months=3',
      '/api/analytics/spending-mix?space_ids=personal%2C7&months=6',
    ])
  })
})

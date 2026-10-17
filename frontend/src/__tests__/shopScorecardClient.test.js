import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchShopScorecard } from '../api/client.js'

afterEach(() => vi.restoreAllMocks())

describe('fetchShopScorecard', () => {
  it('asks for 6 months by default and passes any period, including all time (0)', async () => {
    const urls = []
    global.fetch = vi.fn(async (url) => {
      urls.push(String(url).replace(/^.*\/api/, '/api'))
      return { ok: true, status: 200, json: async () => ({}) }
    })

    await fetchShopScorecard()
    await fetchShopScorecard({ months: 12 })
    await fetchShopScorecard({ months: 0 })

    expect(urls).toEqual(['/api/analytics/shops?months=6', '/api/analytics/shops?months=12', '/api/analytics/shops?months=0'])
  })
})

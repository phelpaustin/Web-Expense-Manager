import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchForecast } from '../api/client.js'

afterEach(() => vi.restoreAllMocks())

describe('fetchForecast', () => {
  it('asks with no query by default and passes the dashboard scope', async () => {
    const urls = []
    global.fetch = vi.fn(async (url) => {
      urls.push(String(url).replace(/^.*\/api/, '/api'))
      return { ok: true, status: 200, json: async () => ({}) }
    })

    await fetchForecast()
    await fetchForecast({ scope: 'personal' })
    await fetchForecast({ spaceIds: ['personal', 7] })

    expect(urls).toEqual([
      '/api/analytics/forecast',
      '/api/analytics/forecast?scope=personal',
      '/api/analytics/forecast?space_ids=personal%2C7',
    ])
  })
})

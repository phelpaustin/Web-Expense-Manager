import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchCategoryChange } from '../api/client.js'

function fakeFetch() {
  const urls = []
  global.fetch = vi.fn(async (url) => {
    urls.push(String(url).replace(/^.*\/api/, '/api'))
    return { ok: true, status: 200, json: async () => ({}) }
  })
  return urls
}

afterEach(() => vi.restoreAllMocks())

describe('fetchCategoryChange', () => {
  it('asks for the default month with no query at all', async () => {
    const urls = fakeFetch()
    await fetchCategoryChange()
    expect(urls).toEqual(['/api/analytics/category-change'])
  })

  it('passes the month and the dashboard scope', async () => {
    const urls = fakeFetch()
    await fetchCategoryChange({ month: '2026-09', scope: 'personal' })
    await fetchCategoryChange({ month: '2026-09', spaceIds: ['personal', 7] })
    await fetchCategoryChange({ scope: 'all' })
    expect(urls).toEqual([
      '/api/analytics/category-change?scope=personal&month=2026-09',
      '/api/analytics/category-change?space_ids=personal%2C7&month=2026-09',
      '/api/analytics/category-change',
    ])
  })
})

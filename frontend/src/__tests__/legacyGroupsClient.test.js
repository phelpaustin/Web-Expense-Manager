import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { resolveLegacyGroups } from '../api/client.js'

beforeEach(() => localStorage.setItem('expense_manager_token', 'tok'))
afterEach(() => vi.restoreAllMocks())

describe('resolveLegacyGroups', () => {
  it('sends the decision as JSON, which the server requires', async () => {
    global.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ changed: 2 }) }))
    await expect(resolveLegacyGroups('split', [4, 5])).resolves.toEqual({ changed: 2 })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toContain('/api/bills/legacy-groups/resolve')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ action: 'split', ids: [4, 5] })
  })
})

import { describe, it, expect, vi, afterEach } from 'vitest'
import { addCategory } from '../api/client.js'

afterEach(() => vi.restoreAllMocks())

describe('addCategory', () => {
  it('surfaces the server\'s "already present" message unchanged', async () => {
    localStorage.setItem('expense_token', 'tok')
    global.fetch = vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ detail: '“Milk” is already present.' }) }))

    await expect(addCategory('milk')).rejects.toThrow('“Milk” is already present.')
  })
})

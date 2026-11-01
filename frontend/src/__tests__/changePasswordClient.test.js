import { describe, it, expect, vi, afterEach } from 'vitest'
import { changePassword } from '../api/client.js'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('changePassword', () => {
  it('stores the fresh token so this device stays signed in', async () => {
    localStorage.setItem('expense_token', 'old-token')
    global.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ changed: true, access_token: 'new-token' }) }))
    await changePassword('old-password-1', 'new-password-1')
    const sent = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(sent).toEqual({ current_password: 'old-password-1', new_password: 'new-password-1' })
    expect(localStorage.getItem('expense_token')).toBe('new-token')
  })
})

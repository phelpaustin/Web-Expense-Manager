import { describe, it, expect, vi, afterEach } from 'vitest'
import { deleteAccount } from '../api/client.js'

function capture() {
  global.fetch = vi.fn(async () => ({ ok: true, status: 204, json: async () => null }))
  return () => JSON.parse(global.fetch.mock.calls[0][1].body)
}

afterEach(() => vi.restoreAllMocks())

describe('deleteAccount', () => {
  it('sends the password when given a string', async () => {
    const body = capture()
    await deleteAccount('hunter2-hunter2')
    expect(body()).toEqual({ password: 'hunter2-hunter2' })
  })

  it('sends a Google credential for accounts without a password', async () => {
    const body = capture()
    await deleteAccount({ googleCredential: 'g-token' })
    expect(body()).toEqual({ google_credential: 'g-token' })
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createExpense, updateExpense } from '../api/client.js'

function respond(status, body) {
  global.fetch = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new Error('no body')
      return body
    },
    text: async () => JSON.stringify(body),
  }))
}

beforeEach(() => localStorage.setItem('expense_manager_token', 'tok'))
afterEach(() => vi.restoreAllMocks())

describe('API error messages', () => {
  it('shows a string detail as is', async () => {
    respond(409, { detail: 'This bill has already been itemised' })
    await expect(updateExpense(1, {})).rejects.toThrow('This bill has already been itemised')
  })

  it('turns FastAPI 422 validation lists into readable text (field: message)', async () => {
    respond(422, {
      detail: [{ loc: ['body', 'amount'], msg: 'Value error, cannot be null', type: 'value_error' }],
    })
    await expect(updateExpense(1, { amount: null })).rejects.toThrow('amount: cannot be null')
  })

  it('joins several validation errors', async () => {
    respond(422, {
      detail: [
        { loc: ['body', 'amount'], msg: 'Input should be greater than 0' },
        { loc: ['body', 'currency'], msg: 'Value error, Currency XXX is not supported for conversion' },
      ],
    })
    await expect(createExpense({})).rejects.toThrow(/amount: Input should be greater than 0; currency: Currency XXX is not supported/)
  })

  it('falls back to a generic message for a non-JSON error body', async () => {
    respond(500, undefined)
    await expect(updateExpense(1, {})).rejects.toThrow('Request failed')
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

import { fetchMe, fetchSummary, forgotPassword, onSessionExpired } from '../api/client.js'
import { useAuth } from '../hooks/useAuth.js'

const TOKEN_KEY = 'expense_token'

// A tiny fake backend: responders are keyed by path; anything else is a 200 with [].
function fakeServer(routes) {
  const calls = []
  global.fetch = vi.fn(async (url, init = {}) => {
    const path = String(url).replace(/^.*\/api/, '/api')
    calls.push({ path, method: init.method || 'GET', headers: init.headers || {} })
    const route = routes[path]
    const out = typeof route === 'function' ? route() : route
    if (out instanceof Error) throw out
    const status = out?.status ?? 200
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => out?.body ?? [],
    }
  })
  return calls
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('request(): a rejected session', () => {
  it('clears the token, notifies once, and does not call /auth/logout', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    const calls = fakeServer({ '/api/auth/me': { status: 401, body: { detail: 'Invalid token' } } })
    const listener = vi.fn()
    const off = onSessionExpired(listener)

    // The dashboard fires many requests at once; they all get a 401.
    const results = await Promise.allSettled([fetchMe(), fetchMe(), fetchMe()])

    expect(results.every((r) => r.status === 'rejected')).toBe(true)
    expect(results[0].reason.status).toBe(401)
    expect(results[0].reason.message).toMatch(/Session expired/)
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(listener).toHaveBeenCalledTimes(1)
    // Revoking an already-rejected token would only bump session_version for nothing.
    expect(calls.some((c) => c.path === '/api/auth/logout')).toBe(false)
    off()
  })

  it('leaves a newer session alone when a stale request 401s after a re-login', async () => {
    localStorage.setItem(TOKEN_KEY, 'old')
    fakeServer({
      '/api/auth/me': () => {
        localStorage.setItem(TOKEN_KEY, 'new') // the user signed in again while this was in flight
        return { status: 401, body: {} }
      },
    })
    const listener = vi.fn()
    const off = onSessionExpired(listener)

    await expect(fetchMe()).rejects.toThrow(/Session expired/)

    expect(localStorage.getItem(TOKEN_KEY)).toBe('new')
    expect(listener).not.toHaveBeenCalled()
    off()
  })

  it('treats a 401 on a request with no token as an ordinary error', async () => {
    fakeServer({ '/api/auth/forgot-password': { status: 401, body: { detail: 'Nope' } } })
    const listener = vi.fn()
    const off = onSessionExpired(listener)

    await expect(forgotPassword('a@b.com')).rejects.toThrow('Nope')

    expect(listener).not.toHaveBeenCalled()
    off()
  })

  it('keeps the token on a server error and reports its status', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    fakeServer({ '/api/auth/me': { status: 503, body: { detail: 'Waking up' } } })
    const listener = vi.fn()
    const off = onSessionExpired(listener)

    const err = await fetchMe().catch((e) => e)

    expect(err.status).toBe(503)
    expect(localStorage.getItem(TOKEN_KEY)).toBe('tok')
    expect(listener).not.toHaveBeenCalled()
    off()
  })
})

describe('useAuth', () => {
  const ME = { id: 1, email: 'a@b.com', name: 'A' }

  function mount(overrides = {}) {
    const loadAll = vi.fn(async () => {})
    const resetData = vi.fn()
    const setError = vi.fn()
    const hook = renderHook(() => useAuth(overrides.loadAll || loadAll, overrides.resetData || resetData, setError))
    return { ...hook, loadAll, resetData, setError }
  }

  it('does not log the user out when the server is unreachable on startup', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    const calls = fakeServer({ '/api/auth/me': new TypeError('Failed to fetch') })

    const { result } = mount()
    await waitFor(() => expect(result.current.authChecked).toBe(true))

    expect(localStorage.getItem(TOKEN_KEY)).toBe('tok')
    expect(result.current.user).toBeNull()
    expect(result.current.authError).toMatch(/Can’t reach the server/)
    expect(result.current.sessionNotice).toBeNull()
    expect(calls.some((c) => c.path === '/api/auth/logout')).toBe(false)
  })

  it('does not log the user out on a 5xx during startup, and a retry restores the session', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    let up = false
    const calls = fakeServer({
      '/api/auth/me': () => (up ? { status: 200, body: ME } : { status: 502, body: {} }),
    })

    const { result, loadAll } = mount()
    await waitFor(() => expect(result.current.authError).toBeTruthy())
    expect(localStorage.getItem(TOKEN_KEY)).toBe('tok')
    expect(calls.some((c) => c.path === '/api/auth/logout')).toBe(false)

    up = true
    await act(async () => {
      await result.current.retryAuth()
    })

    expect(result.current.user).toEqual(ME)
    expect(result.current.authError).toBeNull()
    expect(loadAll).toHaveBeenCalledTimes(1)
  })

  it('shows the session-expired notice when the saved token is rejected on startup', async () => {
    localStorage.setItem(TOKEN_KEY, 'stale')
    fakeServer({ '/api/auth/me': { status: 401, body: { detail: 'Invalid token' } } })

    const { result } = mount()
    await waitFor(() => expect(result.current.authChecked).toBe(true))

    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(result.current.user).toBeNull()
    expect(result.current.authError).toBeNull()
    expect(result.current.sessionNotice).toMatch(/session has expired/i)
  })

  it('returns to the sign-in screen and clears data when the session is rejected mid-use', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    let rejected = false
    fakeServer({
      '/api/auth/me': { status: 200, body: ME },
      '/api/expenses/summary': () => (rejected ? { status: 401, body: {} } : { status: 200, body: {} }),
    })

    const { result, resetData } = mount()
    await waitFor(() => expect(result.current.user).toEqual(ME))

    rejected = true
    await act(async () => {
      await fetchSummary().catch(() => {})
    })

    expect(result.current.user).toBeNull()
    expect(resetData).toHaveBeenCalledTimes(1)
    expect(result.current.sessionNotice).toMatch(/session has expired/i)
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it('clears the notice once the user signs in again', async () => {
    localStorage.setItem(TOKEN_KEY, 'stale')
    fakeServer({ '/api/auth/me': { status: 401, body: {} } })
    const { result } = mount()
    await waitFor(() => expect(result.current.sessionNotice).toBeTruthy())

    localStorage.setItem(TOKEN_KEY, 'fresh')
    fakeServer({ '/api/auth/me': { status: 200, body: ME } })
    await act(async () => {
      result.current.handleAuthed()
    })

    await waitFor(() => expect(result.current.user).toEqual(ME))
    expect(result.current.sessionNotice).toBeNull()
  })
})

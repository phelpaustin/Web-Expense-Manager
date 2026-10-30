import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { viewReceipt } from '../api/client.js'

let tab
beforeEach(() => {
  vi.useFakeTimers()
  tab = { opener: 'parent', location: { href: '' }, close: vi.fn() }
  window.open = vi.fn(() => tab)
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:receipt')
  globalThis.URL.revokeObjectURL = vi.fn()
  globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(['pdf']) }))
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('viewReceipt', () => {
  it('opens the tab before the download, so a popup blocker allows it, and points it at the file', async () => {
    let openedBeforeFetch = false
    globalThis.fetch = vi.fn(async () => {
      openedBeforeFetch = window.open.mock.calls.length === 1
      return { ok: true, status: 200, blob: async () => new Blob(['pdf']) }
    })
    await viewReceipt(7)
    expect(openedBeforeFetch).toBe(true)
    expect(window.open).toHaveBeenCalledTimes(1)
    expect(tab.location.href).toBe('blob:receipt')
    expect(tab.opener).toBeNull()
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/api/pending-bills/7/receipt')
  })

  it('lets go of the file after a minute, not before', async () => {
    await viewReceipt(7)
    vi.advanceTimersByTime(59_000)
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2_000)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:receipt')
  })

  it('closes the empty tab and reports the error when the receipt cannot be loaded', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 404 }))
    await expect(viewReceipt(7)).rejects.toThrow('Could not load receipt')
    expect(tab.close).toHaveBeenCalled()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('closes the tab when the network fails too', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('offline') })
    await expect(viewReceipt(7)).rejects.toThrow('offline')
    expect(tab.close).toHaveBeenCalled()
  })

  it('still works when the browser refuses to open a tab up front', async () => {
    window.open = vi.fn().mockReturnValueOnce(null).mockReturnValue(tab)
    await viewReceipt(7)
    expect(window.open).toHaveBeenLastCalledWith('blob:receipt', '_blank')
  })
})

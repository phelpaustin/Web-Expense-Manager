import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchReport, downloadReport, exportExpenses } from '../api/client.js'

let calls
beforeEach(() => {
  calls = []
  globalThis.fetch = vi.fn(async (url, init) => {
    calls.push({ url, init })
    return { ok: true, status: 200, json: async () => ({ ok: true }), blob: async () => new Blob(['x']), headers: new Headers({ 'content-type': 'application/json' }), text: async () => '{}' }
  })
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:x')
  globalThis.URL.revokeObjectURL = vi.fn()
})
afterEach(() => vi.restoreAllMocks())

describe('report requests', () => {
  it('asks for a year, a month, and the scope', async () => {
    await fetchReport({ year: 2026 })
    await fetchReport({ year: 2026, month: 3, scope: 'personal' })
    await fetchReport({ year: 2025, spaceIds: ['personal', '4'] })
    await fetchReport()
    expect(calls.map((c) => c.url.replace(/^.*\/api/, '/api'))).toEqual([
      '/api/reports?year=2026',
      '/api/reports?scope=personal&year=2026&month=3',
      '/api/reports?space_ids=personal%2C4&year=2025',
      '/api/reports',
    ])
  })

  it('downloads a file named after the period, through a temporary link', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await downloadReport({ format: 'xlsx', year: 2026 })
    await downloadReport({ format: 'pdf', year: 2026, month: 3, scope: 'personal' })
    expect(calls.map((c) => c.url.replace(/^.*\/api/, '/api'))).toEqual([
      '/api/reports/export?format=xlsx&year=2026',
      '/api/reports/export?scope=personal&format=pdf&year=2026&month=3',
    ])
    expect(click).toHaveBeenCalledTimes(2)
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
    expect(document.querySelector('a[download]')).toBeNull()
  })

  it('names the saved file', async () => {
    const names = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { names.push(this.download) })
    await downloadReport({ format: 'xlsx', year: 2026 })
    await downloadReport({ format: 'pdf', year: 2026, month: 3 })
    await downloadReport({ format: 'pdf', year: 2026, month: 11 })
    await exportExpenses('xlsx')
    await exportExpenses('csv')
    expect(names).toEqual(['report-2026.xlsx', 'report-2026-03.pdf', 'report-2026-11.pdf', 'expenses.xlsx', 'expenses.csv'])
  })

  it('fails with a readable message when the server says no', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500 }))
    await expect(downloadReport({ format: 'pdf', year: 2026 })).rejects.toThrow('Couldn’t create the report file')
    await expect(exportExpenses('csv')).rejects.toThrow('Export failed')
  })
})

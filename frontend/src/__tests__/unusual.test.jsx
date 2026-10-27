import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { allClearText, describeDuplicate, describeUnusual, entryName, hasFindings, ratioText } from '../unusual.js'
import UnusualPanel from '../components/UnusualPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())

const big = (extra = {}) => ({ id: 1, date: '2026-10-10', category: 'Food', description: 'Dinner', shop: 'Bistro', amount: 450, usual: 100, ratio: 4.5, compared_with: 12, ...extra })
const dup = (extra = {}) => ({ date: '2026-10-09', amount: 20, description: 'Milk', shop: 'ICA', category: 'Food', count: 2, ids: [3, 4], ...extra })
const data = (unusualItems, dupItems, extra = {}) => ({
  unusual: { recent_days: 30, checked: 7, items: unusualItems, total_found: unusualItems.length },
  duplicates: { recent_days: 60, items: dupItems, total_found: dupItems.length },
  currency: 'USD', unconverted_count: 0, ...extra,
})
const show = () => render(<MemoryRouter><UnusualPanel scope="personal" refreshKey={0} /></MemoryRouter>)

describe('unusual helpers', () => {
  it('names an entry from what it has', () => {
    expect(entryName(big())).toBe('Dinner at Bistro')
    expect(entryName(big({ shop: '' }))).toBe('Dinner')
    expect(entryName(big({ description: '', shop: '' }))).toBe('Food')
    expect(entryName(big({ description: 'ICA', shop: 'ICA' }))).toBe('ICA')
  })

  it('writes the ratio with at most one decimal', () => {
    expect(ratioText(4.46)).toBe('4.5×')
    expect(ratioText(3)).toBe('3×')
    expect(ratioText(3.04)).toBe('3×')
  })

  it('describes findings in a sentence', () => {
    expect(describeUnusual(big())).toBe('Dinner at Bistro on 2026-10-10, $450.00, is 4.5× your usual Food expense of about $100.00.')
    expect(describeDuplicate(dup())).toBe('2 entries of Milk at ICA for $20.00 on 2026-10-09.')
  })

  it('says all is clear, and when there are findings', () => {
    expect(hasFindings(data([], []))).toBe(false)
    expect(hasFindings(data([big()], []))).toBe(true)
    expect(hasFindings(data([], [dup()]))).toBe(true)
    expect(allClearText(data([], []))).toContain('7 expenses from the last 30 days')
    expect(allClearText(data([], [], { unusual: { recent_days: 30, checked: 1, items: [], total_found: 0 } }))).toContain('1 expense from')
  })
})

describe('UnusualPanel', () => {
  it('lists both kinds of finding', async () => {
    client.fetchUnusual.mockResolvedValue(data([big()], [dup()]))
    show()
    await screen.findByText('Bigger than usual')
    expect(screen.getByLabelText(describeUnusual(big()))).toBeTruthy()
    expect(screen.getByText('Entered twice?')).toBeTruthy()
    expect(screen.getByLabelText(describeDuplicate(dup()))).toBeTruthy()
    expect(screen.getByText('2×')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Review them under Spending/ }).getAttribute('href')).toBe('/spending?view=items')
  })

  it('shows only the section that has something', async () => {
    client.fetchUnusual.mockResolvedValue(data([big()], []))
    show()
    await screen.findByText('Bigger than usual')
    expect(screen.queryByText('Entered twice?')).toBeNull()
  })

  it('says all is clear instead of an empty table', async () => {
    client.fetchUnusual.mockResolvedValue(data([], []))
    show()
    await screen.findByText(/Nothing stands out/)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('says when there are more than are shown', async () => {
    client.fetchUnusual.mockResolvedValue(data([big()], [dup()], { unusual: { recent_days: 30, checked: 9, items: [big()], total_found: 4 } }))
    show()
    await screen.findByText('Showing the 1 biggest of 4.')
  })

  it('shows Loading until the data has its shape, and an error when the request fails', async () => {
    client.fetchUnusual.mockResolvedValue({})
    const { unmount } = show()
    expect(screen.getByText('Loading…')).toBeTruthy()
    unmount()
    client.fetchUnusual.mockRejectedValue(new Error('boom'))
    show()
    await waitFor(() => expect(screen.getByText(/Couldn’t load this: boom/)).toBeTruthy())
  })

  it('passes the scope on', async () => {
    client.fetchUnusual.mockResolvedValue(data([], []))
    show()
    await screen.findByText(/Nothing stands out/)
    expect(client.fetchUnusual).toHaveBeenCalledWith({ scope: 'personal', spaceIds: undefined })
  })
})

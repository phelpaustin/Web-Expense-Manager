import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { allClearText, describeDuplicate, describeUnusual, dismissedLabel, dismissedList, entryName, hasFindings, ratioText } from '../unusual.js'
import UnusualPanel from '../components/UnusualPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())

const big = (extra = {}) => ({ id: 1, date: '2026-10-10', category: 'Food', description: 'Dinner', shop: 'Bistro', amount: 450, usual: 100, ratio: 4.5, compared_with: 12, ...extra })
const dup = (extra = {}) => ({ date: '2026-10-09', amount: 20, description: 'Milk', shop: 'ICA', category: 'Food', count: 2, ids: [3, 4], key: 'k'.repeat(64), was_dismissed: false, ...extra })
const data = (unusualItems, dupItems, extra = {}) => ({
  unusual: { recent_days: 30, checked: 7, items: unusualItems, total_found: unusualItems.length },
  duplicates: { recent_days: 60, items: dupItems, total_found: dupItems.length, dismissed: [], dismissed_total: 0 },
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

describe('not a duplicate', () => {
  const withDismissed = (items, dismissed) => {
    const d = data([], items)
    d.duplicates.dismissed = dismissed
    d.duplicates.dismissed_total = dismissed.length
    return d
  }

  it('words the dismissed count', () => {
    expect(dismissedLabel(1)).toBe('1 marked as not a duplicate')
    expect(dismissedLabel(3)).toBe('3 marked as not a duplicate')
    expect(dismissedList({ duplicates: {} })).toEqual([])
    expect(dismissedList(withDismissed([], [dup()]))).toHaveLength(1)
  })

  it('sends the group to the server and reloads the list', async () => {
    client.fetchUnusual.mockResolvedValueOnce(data([], [dup()])).mockResolvedValueOnce(withDismissed([], [dup()]))
    client.dismissExpenseDuplicate.mockResolvedValue({ dismissed: true })
    show()
    fireEvent.click(await screen.findByRole('button', { name: /Not a duplicate: 2 entries of Milk/ }))
    await screen.findByText('1 marked as not a duplicate')
    expect(client.dismissExpenseDuplicate).toHaveBeenCalledWith({ key: 'k'.repeat(64), day: '2026-10-09', count: 2 })
    expect(client.fetchUnusual).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('Entered twice?')).toBeNull()
    expect(screen.getByText(/Nothing stands out/)).toBeTruthy()
  })

  it('brings a group back with Undo', async () => {
    client.fetchUnusual.mockResolvedValueOnce(withDismissed([], [dup()])).mockResolvedValueOnce(data([], [dup()]))
    client.undoDismissExpenseDuplicate.mockResolvedValue(null)
    show()
    fireEvent.click(await screen.findByRole('button', { name: /Undo: 2 entries of Milk/ }))
    await screen.findByText('Entered twice?')
    expect(client.undoDismissExpenseDuplicate).toHaveBeenCalledWith('k'.repeat(64))
    expect(screen.queryByText('1 marked as not a duplicate')).toBeNull()
  })

  it('keeps the list and says so when saving fails', async () => {
    client.fetchUnusual.mockResolvedValue(data([], [dup()]))
    client.dismissExpenseDuplicate.mockRejectedValue(new Error('offline'))
    show()
    fireEvent.click(await screen.findByRole('button', { name: /Not a duplicate/ }))
    await screen.findByText(/Couldn’t save that: offline/)
    expect(screen.getByText('Entered twice?')).toBeTruthy()
    expect(client.fetchUnusual).toHaveBeenCalledTimes(1)
  })

  it('says a group came back because of another entry', async () => {
    client.fetchUnusual.mockResolvedValue(data([], [dup({ count: 3, was_dismissed: true })]))
    show()
    await screen.findByText('more since you dismissed it')
  })

  it('shows no dismissed section when there are none, and copes with an older response', async () => {
    client.fetchUnusual.mockResolvedValue(data([], [dup()]))
    const { unmount } = show()
    await screen.findByText('Entered twice?')
    expect(screen.queryByText(/marked as not a duplicate/)).toBeNull()
    unmount()
    const old = data([], [dup({ key: undefined })])
    delete old.duplicates.dismissed
    client.fetchUnusual.mockResolvedValue(old)
    show()
    await screen.findByText('Entered twice?')
    expect(screen.queryByRole('button', { name: /Not a duplicate/ })).toBeNull()
  })
})

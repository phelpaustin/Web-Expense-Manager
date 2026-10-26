import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { dayLabel, dueText, headline, perText, priceChangeText } from '../recurringCosts.js'
import RecurringCostsPanel from '../components/RecurringCostsPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))

const item = (id, name, monthly, extra = {}) => ({
  id, item: name, category: 'Subs', frequency: 'Monthly', amount: monthly, native_amount: monthly, native_currency: 'USD', monthly,
  yearly: monthly * 12, next_due: '2026-11-01', overdue: false, last_paid: '2026-10-01', payments: 3, price_change: null, ...extra,
})
const RISE = { from: 100, to: 120, since: '2026-09-01', currency: 'USD', pct_change: 20, direction: 'up' }
const DATA = {
  count: 3, monthly_total: 550, yearly_total: 6600, price_rises: 1, currency: 'USD', unconverted_count: 0,
  items: [
    item(1, 'Gym', 300),
    item(2, 'Netflix', 120, { price_change: RISE }),
    item(3, 'Insurance', 100, { frequency: 'Yearly', native_amount: 1200, next_due: '2026-09-20', overdue: true }),
  ],
}
const show = () => render(<MemoryRouter><RecurringCostsPanel refreshKey={null} /></MemoryRouter>)

describe('recurring cost helpers', () => {
  it('writes dates in full', () => {
    expect(dayLabel('2026-11-01')).toBe('1 Nov 2026')
    expect(dayLabel('2026-03-15')).toBe('15 Mar 2026')
    expect(dayLabel(null)).toBe('')
  })

  it('says when a payment is due, and when it is overdue', () => {
    expect(dueText({ next_due: '2026-11-01', overdue: false })).toBe('1 Nov 2026')
    expect(dueText({ next_due: '2026-09-20', overdue: true })).toBe('Overdue since 20 Sep 2026')
    expect(dueText({})).toBe('')
  })

  it('describes a price change in the payment’s own currency', () => {
    expect(priceChangeText(RISE)).toBe('Up 20% since 1 Sep 2026 ($100.00 to $120.00)')
    expect(priceChangeText({ ...RISE, direction: 'down', pct_change: -20, from: 120, to: 100 })).toBe('Down 20% since 1 Sep 2026 ($120.00 to $100.00)')
    expect(priceChangeText({ ...RISE, pct_change: null })).toBe('Up since 1 Sep 2026 ($100.00 to $120.00)')
    expect(priceChangeText(null)).toBe('')
  })

  it('has a headline for none, one and many', () => {
    expect(headline({ count: 0 })).toBe('No recurring payments yet.')
    expect(headline({ count: 1, monthly_total: 5, yearly_total: 60 })).toBe('1 recurring payment costs about $5.00 a month ($60.00 a year).')
    expect(headline(DATA)).toBe('3 recurring payments cost about $550.00 a month ($6,600.00 a year).')
  })

  it('puts a frequency in words, and shows an unknown one as it is', () => {
    expect(perText('Bi-weekly')).toBe('every 2 weeks')
    expect(perText('Yearly')).toBe('a year')
    expect(perText('Sometimes')).toBe('Sometimes')
  })
})

describe('RecurringCostsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchRecurringCosts.mockImplementation(async () => DATA)
  })

  it('shows the totals and one row per payment', async () => {
    show()
    expect(await screen.findByTestId('recurring-headline')).toHaveProperty('textContent', '3 recurring payments cost about $550.00 a month ($6,600.00 a year).')
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows.map((r) => within(r).getAllByRole('cell')[0].textContent.slice(0, 5))).toEqual(['Gym', 'Netfl', 'Insur'])
    const cells = (r) => within(r).getAllByRole('cell').map((c) => c.textContent)
    expect(cells(rows[0]).slice(1)).toEqual(['$300.00 a month', '$300.00', '1 Nov 2026'])
    // a yearly payment shows its yearly amount, and its monthly share
    expect(cells(rows[2]).slice(1)).toEqual(['$1,200.00 a year', '$100.00', 'Overdue since 20 Sep 2026'])
  })

  it('points out price rises', async () => {
    show()
    expect(await screen.findByRole('status')).toHaveProperty('textContent', '1 price rise: Netflix +20%.')
    expect(screen.getByText(/Up 20% since 1 Sep 2026/).className).toContain('up')
  })

  it('marks an overdue payment', async () => {
    show()
    expect((await screen.findByText('Overdue since 20 Sep 2026')).className).toContain('up')
    const gym = screen.getAllByRole('row')[1]
    expect(within(gym).getByText('1 Nov 2026').className).not.toContain('up')
  })

  it('links to the Recurring page', async () => {
    show()
    expect((await screen.findByRole('link', { name: 'Manage recurring' })).getAttribute('href')).toBe('/recurring')
  })

  it('has nothing to list when there are no recurring payments', async () => {
    client.fetchRecurringCosts.mockImplementation(async () => ({ ...DATA, count: 0, monthly_total: 0, yearly_total: 0, price_rises: 0, items: [] }))
    show()
    expect(await screen.findByText('No recurring payments yet.')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('mentions payments left out for lack of an exchange rate', async () => {
    client.fetchRecurringCosts.mockImplementation(async () => ({ ...DATA, unconverted_count: 1 }))
    show()
    expect(await screen.findByText(/1 recurring payment in a currency without an exchange rate is left out/)).toBeTruthy()
  })

  it('shows the error, and copes with an answer that has no list', async () => {
    client.fetchRecurringCosts.mockImplementation(async () => {
      throw new Error('server down')
    })
    const { unmount } = show()
    expect(await screen.findByText(/Couldn’t load the recurring costs: server down/)).toBeTruthy()
    unmount()
    client.fetchRecurringCosts.mockImplementation(async () => ({}))
    show()
    expect(await screen.findByText('Loading…')).toBeTruthy()
  })
})

import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { describeRise, isBigRise, riseName, summaryText, windowLabel } from '../priceRises.js'
import PriceRisesPanel from '../components/PriceRisesPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))

const rise = (item, pct, extra = {}) => ({
  item, brand: '', shop: 'ICA', unit: 'Litre', category: 'Food', latest_price: 13, latest_date: '2026-10-10', usual_price: 10,
  rise_per_unit: 3, rise_pct: pct, earlier_purchases: 3, ...extra,
})
const DATA = { recent_days: 30, min_rise_pct: 10, checked: 5, items: [rise('Eggs', 40, { brand: 'Kronägg' }), rise('Milk', 12)], total_found: 2, currency: 'USD' }

describe('price rise helpers', () => {
  it('names the item with its brand when it has one', () => {
    expect(riseName(rise('Eggs', 40, { brand: 'Kronägg' }))).toBe('Eggs (Kronägg)')
    expect(riseName(rise('Milk', 12))).toBe('Milk')
  })

  it('describes a rise in a sentence', () => {
    expect(describeRise(rise('Milk', 30))).toBe('Milk at ICA now costs $13.00 per Litre, 30% more than your usual $10.00.')
  })

  it('treats 25% and over as big, as the bell does', () => {
    expect(isBigRise({ rise_pct: 25 })).toBe(true)
    expect(isBigRise({ rise_pct: 24.9 })).toBe(false)
  })

  it('labels the window, including one that is not on the list', () => {
    expect(windowLabel(30)).toBe('Last 30 days')
    expect(windowLabel(45)).toBe('Last 45 days')
  })

  it('says why there is nothing to show', () => {
    expect(summaryText({ recent_days: 30, min_rise_pct: 10, checked: 0, items: [] })).toContain('Nothing to compare yet')
    expect(summaryText({ recent_days: 30, min_rise_pct: 10, checked: 1, items: [] })).toBe('No price rises in the last 30 days: 1 item checked, none up 10% or more.')
    expect(summaryText({ recent_days: 7, min_rise_pct: 10, checked: 4, items: [] })).toContain('4 items checked')
    expect(summaryText({ recent_days: 30, min_rise_pct: 10, checked: 4, items: [rise('Milk', 12)] })).toBe('')
  })
})

describe('PriceRisesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchPriceRises.mockImplementation(async () => DATA)
  })

  it('lists each rise with the shop, the new price, the usual price and the rise', async () => {
    render(<PriceRisesPanel refreshKey={null} />)
    const rows = (await screen.findAllByRole('row')).slice(1)
    const cells = (r) => within(r).getAllByRole('cell').map((c) => c.textContent)
    expect(cells(rows[0])).toEqual(['Eggs (Kronägg)per Litre', 'ICA', '$13.00', '$10.00' + '3 earlier', '+40%' + '+$3.00'])
    expect(rows[1].getAttribute('aria-label')).toBe('Milk at ICA now costs $13.00 per Litre, 12% more than your usual $10.00.')
    expect(client.fetchPriceRises).toHaveBeenCalledWith({ recentDays: 30 })
  })

  it('marks a big rise more strongly than a small one', async () => {
    render(<PriceRisesPanel refreshKey={null} />)
    const rows = (await screen.findAllByRole('row')).slice(1)
    expect(within(rows[0]).getByText(/\+40%/).className).toContain('price-rise-big')
    expect(within(rows[1]).getByText(/\+12%/).className).not.toContain('price-rise-big')
  })

  it('looks at the window you choose', async () => {
    render(<PriceRisesPanel refreshKey={null} />)
    await screen.findAllByRole('row')
    fireEvent.change(screen.getByLabelText('Price rises window'), { target: { value: '90' } })
    await waitFor(() => expect(client.fetchPriceRises).toHaveBeenLastCalledWith({ recentDays: 90 }))
  })

  it('reads again when told the data changed', async () => {
    const { rerender } = render(<PriceRisesPanel refreshKey={1} />)
    await screen.findAllByRole('row')
    rerender(<PriceRisesPanel refreshKey={2} />)
    await waitFor(() => expect(client.fetchPriceRises).toHaveBeenCalledTimes(2))
  })

  it('says when only the biggest are shown', async () => {
    client.fetchPriceRises.mockImplementation(async () => ({ ...DATA, total_found: 9 }))
    render(<PriceRisesPanel refreshKey={null} />)
    expect(await screen.findByText('Showing the 2 biggest of 9.')).toBeTruthy()
  })

  it('says so, instead of an empty table, when nothing went up', async () => {
    client.fetchPriceRises.mockImplementation(async () => ({ ...DATA, items: [], total_found: 0 }))
    render(<PriceRisesPanel refreshKey={null} />)
    expect(await screen.findByText(/No price rises in the last 30 days: 5 items checked/)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('shows the error, and copes with an answer that has no list', async () => {
    client.fetchPriceRises.mockImplementation(async () => {
      throw new Error('server down')
    })
    const { unmount } = render(<PriceRisesPanel refreshKey={null} />)
    expect(await screen.findByText(/Couldn’t load the price rises: server down/)).toBeTruthy()
    unmount()
    client.fetchPriceRises.mockImplementation(async () => ({}))
    render(<PriceRisesPanel refreshKey={null} />)
    expect(await screen.findByText('Loading…')).toBeTruthy()
  })
})

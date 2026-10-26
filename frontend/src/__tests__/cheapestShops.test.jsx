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
import { describeSaving, itemName, lookbackLabel, summaryText, timesText } from '../cheapestShops.js'
import CheapestShopsPanel from '../components/CheapestShopsPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))

const shop = (name, avg, n) => ({ shop: name, avg_price: avg, times_bought: n, last_date: '2026-09-10' })
const MILK = {
  item: 'Milk', brand: '', unit: 'Litre', category: 'Food', shops_compared: 2,
  cheapest: shop('Lidl', 12, 1), usual: shop('ICA', 15, 3), saving_per_unit: 3, saving_pct: 20,
}
const EGGS = { ...MILK, item: 'Eggs', brand: 'Kronägg', unit: 'Count', cheapest: shop('Coop', 2, 4), usual: shop('ICA', 4, 2), saving_per_unit: 2, saving_pct: 50 }
const DATA = { months: 12, compared: 3, already_cheapest: 1, items: [EGGS, MILK], total_found: 2, currency: 'USD' }

describe('cheapest shop helpers', () => {
  it('names the item with its brand when it has one', () => {
    expect(itemName(MILK)).toBe('Milk')
    expect(itemName(EGGS)).toBe('Eggs (Kronägg)')
  })

  it('counts purchases in words', () => {
    expect(timesText(1)).toBe('once')
    expect(timesText(3)).toBe('3 times')
  })

  it('labels the look-back, including one that is not on the list', () => {
    expect(lookbackLabel(12)).toBe('Last 12 months')
    expect(lookbackLabel(0)).toBe('All time')
    expect(lookbackLabel(18)).toBe('Last 18 months')
  })

  it('describes a saving in a sentence', () => {
    expect(describeSaving(MILK)).toBe('Milk: Lidl averages $12.00 per Litre, 20% less than ICA ($15.00), where you usually buy it.')
  })

  it('says something useful when there is no table to show', () => {
    expect(summaryText({ compared: 0, items: [], already_cheapest: 0 })).toBe('No item has been bought at more than one shop in this period yet.')
    expect(summaryText({ compared: 1, items: [], already_cheapest: 1 })).toBe('For the 1 item you bought at more than one shop, your usual shop is already about as cheap as any.')
    expect(summaryText({ compared: 4, items: [], already_cheapest: 4 })).toContain('For the 4 items')
    expect(summaryText({ compared: 3, items: [MILK], already_cheapest: 2 })).toBe('For 2 other items your usual shop is already the cheapest.')
    expect(summaryText({ compared: 2, items: [MILK], already_cheapest: 1 })).toBe('For 1 other item your usual shop is already the cheapest.')
    expect(summaryText({ compared: 1, items: [MILK], already_cheapest: 0 })).toBe('')
  })
})

describe('CheapestShopsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchCheapestShops.mockImplementation(async () => DATA)
  })

  it('lists each item with its cheapest shop, your usual shop and the saving', async () => {
    render(<CheapestShopsPanel refreshKey={null} />)
    const rows = (await screen.findAllByRole('row')).slice(1)
    const cells = (r) => within(r).getAllByRole('cell').map((c) => c.textContent)
    expect(cells(rows[0])).toEqual(['Eggs (Kronägg)per Count', 'Coop$2.00, bought 4 times', 'ICA$4.00, bought 2 times', '$2.00' + '50% less'])
    expect(cells(rows[1])).toEqual(['Milkper Litre', 'Lidl$12.00, bought once', 'ICA$15.00, bought 3 times', '$3.00' + '20% less'])
    expect(rows[1].getAttribute('aria-label')).toContain('Lidl averages $12.00 per Litre')
    expect(screen.getByText('For 1 other item your usual shop is already the cheapest.')).toBeTruthy()
    expect(client.fetchCheapestShops).toHaveBeenCalledWith({ months: 12 })
  })

  it('looks back as far as you choose', async () => {
    render(<CheapestShopsPanel refreshKey={null} />)
    await screen.findAllByRole('row')
    fireEvent.change(screen.getByLabelText('Look back'), { target: { value: '0' } })
    await waitFor(() => expect(client.fetchCheapestShops).toHaveBeenLastCalledWith({ months: 0 }))
    fireEvent.change(screen.getByLabelText('Look back'), { target: { value: '3' } })
    await waitFor(() => expect(client.fetchCheapestShops).toHaveBeenLastCalledWith({ months: 3 }))
  })

  it('reads again when told the data changed', async () => {
    const { rerender } = render(<CheapestShopsPanel refreshKey={1} />)
    await screen.findAllByRole('row')
    rerender(<CheapestShopsPanel refreshKey={2} />)
    await waitFor(() => expect(client.fetchCheapestShops).toHaveBeenCalledTimes(2))
  })

  it('says when only some of the biggest are shown', async () => {
    client.fetchCheapestShops.mockImplementation(async () => ({ ...DATA, total_found: 14 }))
    render(<CheapestShopsPanel refreshKey={null} />)
    expect(await screen.findByText('Showing the 2 biggest of 14.')).toBeTruthy()
  })

  it('shows good news instead of an empty table', async () => {
    client.fetchCheapestShops.mockImplementation(async () => ({ ...DATA, items: [], total_found: 0, compared: 2, already_cheapest: 2 }))
    render(<CheapestShopsPanel refreshKey={null} />)
    expect(await screen.findByText(/your usual shop is already about as cheap as any/)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('says so when nothing has been bought at two shops', async () => {
    client.fetchCheapestShops.mockImplementation(async () => ({ ...DATA, items: [], total_found: 0, compared: 0, already_cheapest: 0 }))
    render(<CheapestShopsPanel refreshKey={null} />)
    expect(await screen.findByText('No item has been bought at more than one shop in this period yet.')).toBeTruthy()
  })

  it('shows the error, and copes with an answer that has no list', async () => {
    client.fetchCheapestShops.mockImplementation(async () => {
      throw new Error('server down')
    })
    const { unmount } = render(<CheapestShopsPanel refreshKey={null} />)
    expect(await screen.findByText(/Couldn’t load the shop comparison: server down/)).toBeTruthy()
    unmount()
    client.fetchCheapestShops.mockImplementation(async () => ({}))
    render(<CheapestShopsPanel refreshKey={null} />)
    expect(await screen.findByText('Loading…')).toBeTruthy()
  })
})

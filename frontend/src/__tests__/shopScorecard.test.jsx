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
import { priceLevel, describeOpportunity, cheapestOn, PERIODS } from '../shopScorecard.js'
import ShopsPage from '../pages/ShopsPage.jsx'

beforeAll(() => setDisplayCurrency('USD')) // dollars keep the expected text short

const shop = (over = {}) => ({
  shop: 'ICA', spend: 600, share_pct: 45.5, purchases: 9, visits: 4, visits_per_month: 0.7, avg_visit: 150,
  first_visit: '2026-05-01', last_visit: '2026-10-10', price_index: 90.9, items_compared: 5, cheapest_on: 4,
  coverage_pct: 80, potential_saving: 0, ...over,
})

const DATA = {
  period: { months: 6, from: '2026-04-16', to: '2026-10-16' }, available: true, currency: 'SEK', unconverted_count: 0,
  named_spend: 1320, unknown: { spend: 0, purchases: 0 }, min_items_for_index: 3,
  shops: [shop(), shop({ shop: 'Lidl', spend: 720, share_pct: 54.5, price_index: 109.1, cheapest_on: 1, potential_saving: 12 })],
  opportunities: [{ item: 'Rice', brand: 'Uncle Ben', unit: 'Kg', category: 'Food', shop: 'Lidl', price: 60, cheaper_shop: 'ICA', cheaper_price: 50, pay_more_pct: 20, saving: 5 }],
}

describe('priceLevel', () => {
  it('says how much cheaper or dearer, rounded to a whole percent', () => {
    expect(priceLevel({ price_index: 90.9 }, 3)).toEqual({ text: '9% cheaper', tone: 'good' })
    expect(priceLevel({ price_index: 109.1 }, 3)).toEqual({ text: '9% dearer', tone: 'bad' })
    expect(priceLevel({ price_index: 100.4 }, 3)).toEqual({ text: 'About average', tone: 'neutral' })
    expect(priceLevel({ price_index: 99.6 }, 3)).toEqual({ text: 'About average', tone: 'neutral' })
  })

  it('explains why there is no number', () => {
    expect(priceLevel({ price_index: null, items_compared: 0 }, 3)).toMatchObject({ text: '—', tone: 'none', hint: expect.stringMatching(/also bought at another shop/) })
    expect(priceLevel({ price_index: null, items_compared: 2 }, 3).hint).toBe('Needs 3 items bought at other shops too (2 so far)')
  })
})

describe('describeOpportunity and cheapestOn', () => {
  it('describes a saving with the brand when there is one', () => {
    expect(describeOpportunity(DATA.opportunities[0])).toBe(
      'Rice (Uncle Ben): $60.00/Kg at Lidl vs $50.00/Kg at ICA, 20% more. About $5.00 over this period.',
    )
    expect(describeOpportunity({ ...DATA.opportunities[0], brand: '', pay_more_pct: null })).toBe(
      'Rice: $60.00/Kg at Lidl vs $50.00/Kg at ICA. About $5.00 over this period.',
    )
  })

  it('shows how many shared items a shop is cheapest on', () => {
    expect(cheapestOn({ cheapest_on: 4, items_compared: 5 })).toBe('4 of 5')
    expect(cheapestOn({ cheapest_on: 0, items_compared: 0 })).toBe('—')
  })

  it('offers the periods, with all time last', () => {
    expect(PERIODS.map((p) => p.months)).toEqual([1, 3, 6, 12, 0])
  })
})

describe('ShopsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchShopScorecard.mockImplementation(async () => DATA)
  })

  const row = (name) => screen.getByRole('cell', { name }).closest('tr')

  it('starts with the last 6 months and shows a row per shop', async () => {
    render(<ShopsPage onError={vi.fn()} />)

    await screen.findByRole('cell', { name: 'ICA' })

    expect(client.fetchShopScorecard).toHaveBeenCalledWith({ months: 6 })
    expect(screen.getByLabelText('Period').value).toBe('6')
    const ica = within(row('ICA'))
    expect(ica.getByText('$600.00')).toBeTruthy()
    expect(ica.getByText('45.5%')).toBeTruthy()
    expect(ica.getByText('$150.00')).toBeTruthy()
    expect(ica.getByText('9% cheaper')).toBeTruthy()
    expect(ica.getByText('4 of 5')).toBeTruthy()
    const lidl = within(row('Lidl'))
    expect(lidl.getByText('9% dearer')).toBeTruthy()
    expect(lidl.getByText('$12.00')).toBeTruthy() // could save
  })

  it('colours cheaper green and dearer red', async () => {
    render(<ShopsPage onError={vi.fn()} />)
    await screen.findByRole('cell', { name: 'ICA' })

    expect(screen.getByText('9% cheaper').className).toMatch(/down/)
    expect(screen.getByText('9% dearer').className).toMatch(/up/)
  })

  it('shows the biggest savings', async () => {
    render(<ShopsPage onError={vi.fn()} />)

    const list = await screen.findByTestId('opportunities')

    expect(list.textContent).toMatch(/Rice \(Uncle Ben\): \$60\.00\/Kg at Lidl vs \$50\.00\/Kg at ICA/)
  })

  it('reloads for another period, including all time', async () => {
    render(<ShopsPage onError={vi.fn()} />)
    const select = await screen.findByLabelText('Period')

    fireEvent.change(select, { target: { value: '0' } })

    await waitFor(() => expect(client.fetchShopScorecard).toHaveBeenLastCalledWith({ months: 0 }))
    expect([...select.options].map((o) => o.textContent)).toContain('All time')
  })

  it('explains a missing price level, and mentions spending with no shop', async () => {
    client.fetchShopScorecard.mockImplementation(async () => ({
      ...DATA, unknown: { spend: 9000, purchases: 3 },
      shops: [shop({ price_index: null, items_compared: 2, cheapest_on: 1, potential_saving: 0 })],
      opportunities: [],
    }))
    render(<ShopsPage onError={vi.fn()} />)

    await screen.findByRole('cell', { name: 'ICA' })

    expect(screen.getByTitle('Needs 3 items bought at other shops too (2 so far)')).toBeTruthy()
    expect(screen.getByText(/\$9,000\.00 across 3 purchases have no shop recorded/)).toBeTruthy()
    expect(screen.queryByText('💡 Where you could save')).toBeNull()
  })

  it('mentions expenses left out for lack of an exchange rate', async () => {
    client.fetchShopScorecard.mockImplementation(async () => ({ ...DATA, unconverted_count: 1 }))
    render(<ShopsPage onError={vi.fn()} />)

    expect(await screen.findByText(/1 expense in a currency without an exchange rate is left out/)).toBeTruthy()
  })

  it('says so when there is nothing in the period', async () => {
    client.fetchShopScorecard.mockImplementation(async () => ({ ...DATA, available: false, shops: [], opportunities: [] }))
    render(<ShopsPage onError={vi.fn()} />)

    expect(await screen.findByText('No spending with a shop recorded in this period.')).toBeTruthy()
  })

  it('reports a failure to load', async () => {
    client.fetchShopScorecard.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    render(<ShopsPage onError={onError} />)

    await waitFor(() => expect(onError).toHaveBeenCalledWith('boom'))
  })

  it('ignores a slow answer that arrives after a newer choice', async () => {
    let releaseSlow
    client.fetchShopScorecard
      .mockImplementationOnce(async () => DATA)
      .mockImplementationOnce(() => new Promise((r) => { releaseSlow = () => r({ ...DATA, shops: [shop({ shop: 'Slow shop' })] }) }))
      .mockImplementationOnce(async () => ({ ...DATA, shops: [shop({ shop: 'Newest shop' })] }))
    render(<ShopsPage onError={vi.fn()} />)
    const select = await screen.findByLabelText('Period')

    fireEvent.change(select, { target: { value: '3' } }) // slow
    await waitFor(() => expect(client.fetchShopScorecard).toHaveBeenCalledTimes(2))
    fireEvent.change(select, { target: { value: '12' } }) // newer
    await screen.findByRole('cell', { name: 'Newest shop' })
    releaseSlow()
    await new Promise((r) => setTimeout(r, 20))

    expect(screen.getByRole('cell', { name: 'Newest shop' })).toBeTruthy()
    expect(screen.queryByRole('cell', { name: 'Slow shop' })).toBeNull()
  })
})

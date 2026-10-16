import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import PriceDetail from '../components/PriceDetail.jsx'
import PriceTrackerPage from '../pages/PriceTrackerPage.jsx'

const TREND = { item: 'Milk', unit: 'Litre', category: 'Food' }

const OPTIONS = {
  brands: [
    { name: 'Arla', count: 2 },
    { name: 'Local', count: 1 },
    { name: '', count: 1 },
  ],
  shops: [
    { name: 'ICA', count: 2 },
    { name: 'Lidl', count: 1 },
    { name: 'Unknown', count: 1 },
  ],
}

const summary = (over = {}) => ({
  purchases: 4, avg_price: 9.75, min_price: 8, max_price: 12, first_price: 10, last_price: 9,
  change: -1, change_pct: -10, trend: 'Decreasing', first_date: '2026-01-01', last_date: '2026-04-01', volatility: 1.5, ...over,
})

const RESPONSE = {
  options: OPTIONS,
  summary: summary(),
  shops: [
    { shop: 'Lidl', avg_price: 8, min_price: 8, max_price: 8, times_bought: 1 },
    { shop: 'ICA', avg_price: 11, min_price: 10, max_price: 12, times_bought: 2 },
  ],
  history: [
    { date: '2026-01-01', price: 10, shop: 'ICA', brand: 'Arla' },
    { date: '2026-03-01', price: 8, shop: 'Lidl', brand: 'Local' },
  ],
}

const lastCall = () => client.fetchPriceDetail.mock.calls.at(-1)[0]

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchPriceDetail.mockImplementation(async () => RESPONSE)
})

async function open(props = {}) {
  const onError = props.onError || vi.fn()
  render(<PriceDetail trend={TREND} onError={onError} />)
  await screen.findByTestId('selection-summary')
  return { onError }
}

describe('PriceDetail', () => {
  it('starts with everything included', async () => {
    await open()

    expect(lastCall()).toEqual({ item: 'Milk', unit: 'Litre', category: 'Food', brand: null, shops: null })
    for (const name of ['ICA', 'Lidl', 'Unknown']) {
      expect(screen.getByLabelText(new RegExp(`^${name}`)).checked).toBe(true)
    }
    expect(screen.getByLabelText('Brand').value).toBe('__all__')
  })

  it('summarises the selection, the shops and the timeline', async () => {
    await open()

    const text = screen.getByTestId('selection-summary').textContent
    expect(text).toMatch(/4 purchases/)
    expect(text).toMatch(/Decreasing \(-10% since the first purchase\)/)
    expect(screen.getByText('By shop')).toBeTruthy()
    expect(screen.getByText(/2026-01-01 — .*at ICA \(Arla\)/)).toBeTruthy()
  })

  it('narrows to a brand, to no brand, and back to all brands', async () => {
    await open()
    const select = screen.getByLabelText('Brand')

    fireEvent.change(select, { target: { value: 'Arla' } })
    await waitFor(() => expect(lastCall().brand).toBe('Arla'))

    fireEvent.change(select, { target: { value: '' } })
    await waitFor(() => expect(lastCall().brand).toBe(''))
    expect(screen.getByRole('option', { name: /No brand \(1\)/ })).toBeTruthy()

    fireEvent.change(select, { target: { value: '__all__' } })
    await waitFor(() => expect(lastCall().brand).toBeNull())
  })

  it('excludes a shop, keeps the others, and returns to "all" when every shop is back', async () => {
    await open()

    fireEvent.click(screen.getByLabelText(/^Lidl/))
    await waitFor(() => expect(lastCall().shops).toEqual(['ICA', 'Unknown']))
    expect(screen.getByLabelText(/^Lidl/).checked).toBe(false)

    fireEvent.click(screen.getByLabelText(/^Lidl/))
    await waitFor(() => expect(lastCall().shops).toBeNull())
  })

  it('"Include all shops" resets the choice', async () => {
    await open()
    fireEvent.click(screen.getByLabelText(/^ICA/))
    await waitFor(() => expect(lastCall().shops).toEqual(['Lidl', 'Unknown']))

    fireEvent.click(screen.getByRole('button', { name: 'Include all shops' }))

    await waitFor(() => expect(lastCall().shops).toBeNull())
  })

  it('always keeps at least one shop in the comparison', async () => {
    await open()
    fireEvent.click(screen.getByLabelText(/^ICA/))
    await waitFor(() => expect(lastCall().shops).toEqual(['Lidl', 'Unknown']))
    fireEvent.click(screen.getByLabelText(/^Lidl/))
    await waitFor(() => expect(lastCall().shops).toEqual(['Unknown']))

    const last = screen.getByLabelText(/^Unknown/)

    expect(last.disabled).toBe(true)
  })

  it('combines a brand with a shop choice', async () => {
    await open()

    fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Arla' } })
    await waitFor(() => expect(lastCall().brand).toBe('Arla'))
    fireEvent.click(screen.getByLabelText(/^Lidl/))

    await waitFor(() => expect(lastCall()).toMatchObject({ brand: 'Arla', shops: ['ICA', 'Unknown'] }))
  })

  it('offers no choices when there is nothing to choose between', async () => {
    client.fetchPriceDetail.mockImplementation(async () => ({
      ...RESPONSE,
      options: { brands: [{ name: 'Arla', count: 4 }], shops: [{ name: 'ICA', count: 4 }] },
    }))
    await open()

    expect(screen.queryByLabelText('Brand')).toBeNull()
    expect(screen.queryByText('Shops to include')).toBeNull()
  })

  it('says so when the selection matches nothing, and keeps the choices', async () => {
    client.fetchPriceDetail.mockImplementation(async ({ brand }) =>
      brand === 'Local' ? { options: OPTIONS, summary: null, shops: [], history: [] } : RESPONSE,
    )
    await open()

    fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Local' } })

    expect(await screen.findByText('No purchases match this selection.')).toBeTruthy()
    expect(screen.getByLabelText('Brand')).toBeTruthy()
  })

  it('shows a single purchase without a trend', async () => {
    client.fetchPriceDetail.mockImplementation(async () => ({ ...RESPONSE, summary: summary({ purchases: 1, trend: 'Stable', change_pct: 0 }) }))
    await open()

    const text = screen.getByTestId('selection-summary').textContent
    expect(text).toMatch(/1 purchase ·/)
    expect(text).not.toMatch(/Stable/)
  })

  it('ignores a slow answer that arrives after a newer selection', async () => {
    let releaseSlow
    client.fetchPriceDetail
      .mockImplementationOnce(async () => RESPONSE)
      .mockImplementationOnce(() => new Promise((resolve) => { releaseSlow = () => resolve({ ...RESPONSE, summary: summary({ purchases: 99 }) }) }))
      .mockImplementationOnce(async () => ({ ...RESPONSE, summary: summary({ purchases: 2 }) }))
    await open()

    fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Arla' } }) // slow
    await waitFor(() => expect(client.fetchPriceDetail).toHaveBeenCalledTimes(2))
    fireEvent.change(screen.getByLabelText('Brand'), { target: { value: 'Local' } }) // fast, newer
    await waitFor(() => expect(screen.getByTestId('selection-summary').textContent).toMatch(/2 purchases/))
    releaseSlow()
    await new Promise((r) => setTimeout(r, 20))

    expect(screen.getByTestId('selection-summary').textContent).toMatch(/2 purchases/)
  })

  it('reports a failure to load', async () => {
    client.fetchPriceDetail.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    render(<PriceDetail trend={TREND} onError={onError} />)

    await waitFor(() => expect(onError).toHaveBeenCalledWith('boom'))
  })
})

describe('PriceTrackerPage', () => {
  const trend = (item, category = 'Food') => ({
    item, category, unit: 'Litre', first_date: '2026-01-01', last_date: '2026-04-01', first_price: 10, last_price: 12,
    change: 2, change_pct: 20, avg_price: 11, min_price: 10, max_price: 12, volatility: 1, trend: 'Increasing', purchases: 3,
  })

  beforeEach(() => {
    client.fetchPriceTrends.mockResolvedValue([trend('Milk'), trend('Arla Milk'), trend('Bread', 'Bakery')])
  })

  it('lists Milk and Arla Milk as separate items', async () => {
    render(<PriceTrackerPage onError={vi.fn()} />)

    expect(await screen.findByRole('cell', { name: 'Milk' })).toBeTruthy()
    expect(screen.getByRole('cell', { name: 'Arla Milk' })).toBeTruthy()
  })

  it('searches items and categories ignoring case', async () => {
    render(<PriceTrackerPage onError={vi.fn()} />)
    await screen.findByRole('cell', { name: 'Bread' })

    fireEvent.change(screen.getByLabelText('Search items'), { target: { value: 'MILK' } })
    expect(screen.queryByRole('cell', { name: 'Bread' })).toBeNull()
    expect(screen.getByRole('cell', { name: 'Arla Milk' })).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Search items'), { target: { value: '  bAkErY ' } })
    expect(screen.getByRole('cell', { name: 'Bread' })).toBeTruthy()
    expect(screen.queryByRole('cell', { name: 'Milk' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Search items'), { target: { value: 'zzz' } })
    expect(screen.getByText(/No items match “zzz”/)).toBeTruthy()
  })

  it('opens the comparison for the clicked item only, and closes it on a second click', async () => {
    client.fetchPriceDetail.mockImplementation(async () => RESPONSE)
    render(<PriceTrackerPage onError={vi.fn()} />)

    fireEvent.click(await screen.findByRole('cell', { name: 'Arla Milk' }))

    expect(await screen.findByTestId('selection-summary')).toBeTruthy()
    expect(client.fetchPriceDetail).toHaveBeenCalledWith(expect.objectContaining({ item: 'Arla Milk', unit: 'Litre', category: 'Food' }))
    expect(client.fetchPriceDetail).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('cell', { name: 'Arla Milk' }))
    expect(screen.queryByTestId('selection-summary')).toBeNull()
  })
})

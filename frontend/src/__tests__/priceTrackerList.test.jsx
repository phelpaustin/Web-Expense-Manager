import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import PriceTrackerPage from '../pages/PriceTrackerPage.jsx'

const trend = (i) => ({
  item: `Item ${i}`, unit: 'Count', category: 'Food', first_price: 1, last_price: 2,
  change: 1, change_pct: 100, trend: 'Increasing', purchases: 2,
})

describe('PriceTrackerPage long lists', () => {
  it('renders 200 rows first and the rest on "Show more"', async () => {
    client.fetchPriceTrends.mockResolvedValue(Array.from({ length: 450 }, (_, i) => trend(i)))
    client.fetchAliases?.mockResolvedValue?.([])
    render(<PriceTrackerPage onError={() => {}} />)
    await waitFor(() => expect(screen.getByText('Item 0')).toBeTruthy())
    expect(screen.queryByText('Item 200')).toBeNull()
    fireEvent.click(screen.getByText(/Show more \(250 remaining\)/))
    expect(screen.getByText('Item 399')).toBeTruthy()
    fireEvent.click(screen.getByText(/Show more \(50 remaining\)/))
    expect(screen.getByText('Item 449')).toBeTruthy()
    expect(screen.queryByText(/Show more/)).toBeNull()
  })

  it('search still finds items beyond the first page', async () => {
    client.fetchPriceTrends.mockResolvedValue(Array.from({ length: 450 }, (_, i) => trend(i)))
    render(<PriceTrackerPage onError={() => {}} />)
    await waitFor(() => expect(screen.getByText('Item 0')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Search items'), { target: { value: 'item 433' } })
    expect(screen.getByText('Item 433')).toBeTruthy()
  })
})

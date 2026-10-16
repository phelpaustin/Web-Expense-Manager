import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import TidyNames from '../components/TidyNames.jsx'
import PriceTrackerPage from '../pages/PriceTrackerPage.jsx'

const ITEM_GROUP = {
  names: [
    { name: 'Milk', count: 8 },
    { name: 'Milk 1L', count: 3 },
  ],
  suggested: 'Milk',
  reason: 'size',
  total: 11,
}
const SHOP_GROUP = {
  names: [
    { name: 'Willys', count: 5 },
    { name: 'Wilys', count: 1 },
  ],
  suggested: 'Willys',
  reason: 'similar',
  total: 6,
}

function serve({ items = [ITEM_GROUP], shops = [SHOP_GROUP], saved = { items: [], shops: [] } } = {}) {
  client.fetchAliasSuggestions.mockImplementation(async (kind) => ({ groups: kind === 'item' ? items : shops }))
  client.fetchAliases.mockImplementation(async () => saved)
}

beforeEach(() => {
  vi.clearAllMocks()
  serve()
  client.mergeNames.mockImplementation(async () => ({ merged: 1 }))
  client.deleteAlias.mockImplementation(async () => null)
})

async function openPanel(props = {}) {
  const onChanged = props.onChanged || vi.fn()
  const onError = props.onError || vi.fn()
  render(<TidyNames onChanged={onChanged} onError={onError} />)
  fireEvent.click(screen.getByRole('button', { name: /Tidy up names/ }))
  await screen.findByText(/Same name apart from a size/)
  return { onChanged, onError }
}

describe('TidyNames', () => {
  it('loads nothing until it is opened', () => {
    render(<TidyNames onChanged={vi.fn()} onError={vi.fn()} />)

    expect(client.fetchAliasSuggestions).not.toHaveBeenCalled()
    expect(client.fetchAliases).not.toHaveBeenCalled()
  })

  it('offers suggested groups with counts and explains why', async () => {
    await openPanel()

    expect(screen.getByLabelText(/Milk 1L/)).toBeTruthy()
    expect(screen.getByText(/\(8 purchases\)/)).toBeTruthy()
    expect(screen.getByText(/Same name apart from a size/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Items \(1\)/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Shops \(1\)/ })).toBeTruthy()
  })

  it('merges the ticked names into the chosen name, then refreshes the tracker', async () => {
    const { onChanged } = await openPanel()

    fireEvent.click(screen.getByRole('button', { name: /Merge 1 into “Milk”/ }))

    await waitFor(() => expect(client.mergeNames).toHaveBeenCalledWith('item', ['Milk 1L'], 'Milk'))
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    // The panel reloads so merged groups disappear.
    expect(client.fetchAliasSuggestions.mock.calls.length).toBeGreaterThan(2)
  })

  it('lets the user rename the result and leave a name out', async () => {
    await openPanel()

    fireEvent.change(screen.getByLabelText('Name to keep'), { target: { value: 'Whole milk' } })
    expect(screen.getByRole('button', { name: /Merge 2 into “Whole milk”/ })).toBeTruthy()
    fireEvent.click(screen.getByLabelText(/Milk 1L/)) // untick
    fireEvent.click(screen.getByRole('button', { name: /Merge 1 into “Whole milk”/ }))

    await waitFor(() => expect(client.mergeNames).toHaveBeenCalledWith('item', ['Milk'], 'Whole milk'))
  })

  it('cannot merge when nothing differs from the name to keep', async () => {
    await openPanel()

    fireEvent.click(screen.getByLabelText(/Milk 1L/)) // untick the only other name
    const merge = screen.getByRole('button', { name: /^Merge/ })

    expect(merge.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Name to keep'), { target: { value: '   ' } })
    expect(merge.disabled).toBe(true)
  })

  it('switches to shops and merges those as shops', async () => {
    await openPanel()

    fireEvent.click(screen.getByRole('button', { name: /Shops \(1\)/ }))
    expect(screen.getByText(/Look like spelling variants/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Merge 1 into “Willys”/ }))

    await waitFor(() => expect(client.mergeNames).toHaveBeenCalledWith('shop', ['Wilys'], 'Willys'))
  })

  it('shows existing merges and undoes one', async () => {
    serve({ items: [], saved: { items: [{ id: 7, kind: 'item', alias: 'Milk 1L', canonical: 'Milk' }], shops: [] } })
    const onChanged = vi.fn()
    render(<TidyNames onChanged={onChanged} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Tidy up names/ }))

    await screen.findByText(/Milk 1L → Milk/)
    fireEvent.click(screen.getByRole('button', { name: 'Undo merge of Milk 1L' }))

    await waitFor(() => expect(client.deleteAlias).toHaveBeenCalledWith(7))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('says so when there is nothing to tidy', async () => {
    serve({ items: [], shops: [] })
    render(<TidyNames onChanged={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Tidy up names/ }))

    expect(await screen.findByText(/No likely duplicate items found/)).toBeTruthy()
  })

  it('reports a failed merge and does not refresh the tracker', async () => {
    client.mergeNames.mockRejectedValueOnce(new Error('Those names changed while saving; please try again.'))
    const { onChanged, onError } = await openPanel()

    fireEvent.click(screen.getByRole('button', { name: /Merge 1 into “Milk”/ }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Those names changed while saving; please try again.'))
    expect(onChanged).not.toHaveBeenCalled()
    // And the button works again afterwards.
    expect(screen.getByRole('button', { name: /Merge 1 into “Milk”/ }).disabled).toBe(false)
  })

  it('reports a failure to load', async () => {
    client.fetchAliasSuggestions.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    render(<TidyNames onChanged={vi.fn()} onError={onError} />)

    fireEvent.click(screen.getByRole('button', { name: /Tidy up names/ }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith('boom'))
  })
})

describe('PriceTrackerPage with merges', () => {
  const TREND = (purchases) => ({
    item: 'Milk', category: 'Food', unit: 'Litre', first_date: '2026-01-01', last_date: '2026-04-01',
    first_price: 10, last_price: 16, change: 6, change_pct: 60, avg_price: 13, min_price: 10, max_price: 16,
    volatility: 2, trend: 'Increasing', purchases,
  })

  it('reloads the price table after a merge', async () => {
    client.fetchPriceTrends.mockResolvedValueOnce([]).mockResolvedValue([TREND(4)])
    render(<PriceTrackerPage onError={vi.fn()} />)
    await screen.findByText(/Not enough repeat purchases yet/)

    fireEvent.click(screen.getByRole('button', { name: /Tidy up names/ }))
    await screen.findByText(/Same name apart from a size/)
    fireEvent.click(screen.getByRole('button', { name: /Merge 1 into “Milk”/ }))

    await waitFor(() => expect(client.fetchPriceTrends).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Increasing', { exact: false })).toBeTruthy()
    expect(screen.getByText('Litre')).toBeTruthy()
  })
})

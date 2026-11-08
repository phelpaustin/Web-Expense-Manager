import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LegacyGroupsPanel from '../components/expenses/LegacyGroupsPanel.jsx'
import * as client from '../api/client.js'

vi.mock('../api/client.js', () => ({
  fetchLegacyGroups: vi.fn(),
  resolveLegacyGroups: vi.fn(),
}))

const GROUP = {
  id: 7,
  date: '2026-07-10',
  shop: 'Lidl',
  currency: 'SEK',
  amount: 15,
  items: [
    { id: 1, description: 'Milk', category: 'Food', amount: 10 },
    { id: 2, description: 'Eggs', category: 'Food', amount: 5 },
  ],
}

describe('LegacyGroupsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows nothing when no purchase was grouped automatically', async () => {
    client.fetchLegacyGroups.mockResolvedValue([])
    const { container } = render(<LegacyGroupsPanel />)
    await waitFor(() => expect(client.fetchLegacyGroups).toHaveBeenCalled())
    expect(container.innerHTML).toBe('')
  })

  it('lists the grouped purchases after Review and keeps one as a bill', async () => {
    client.fetchLegacyGroups.mockResolvedValueOnce([GROUP]).mockResolvedValue([])
    client.resolveLegacyGroups.mockResolvedValue({ changed: 1 })
    const onChanged = vi.fn()
    render(<LegacyGroupsPanel onChanged={onChanged} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Review' }))
    expect(screen.getByText('Milk')).toBeTruthy()
    expect(screen.getByText(/Lidl/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Keep as one bill' }))
    await waitFor(() => expect(client.resolveLegacyGroups).toHaveBeenCalledWith('keep', [7]))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('Milk')).toBeNull())
  })

  it('splits all of them in one go', async () => {
    client.fetchLegacyGroups.mockResolvedValueOnce([GROUP, { ...GROUP, id: 8 }]).mockResolvedValue([])
    client.resolveLegacyGroups.mockResolvedValue({ changed: 2 })
    render(<LegacyGroupsPanel />)
    fireEvent.click(await screen.findByRole('button', { name: 'Review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Split all' }))
    await waitFor(() => expect(client.resolveLegacyGroups).toHaveBeenCalledWith('split', [7, 8]))
  })

  it('reports a failed decision', async () => {
    client.fetchLegacyGroups.mockResolvedValue([GROUP])
    client.resolveLegacyGroups.mockRejectedValue(new Error('nope'))
    const onError = vi.fn()
    render(<LegacyGroupsPanel onError={onError} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Review' }))
    fireEvent.click(screen.getByRole('button', { name: 'Split' }))
    await waitFor(() => expect(onError).toHaveBeenCalledWith('nope'))
    expect((await screen.findByRole('alert')).textContent).toBe('nope')
  })
})

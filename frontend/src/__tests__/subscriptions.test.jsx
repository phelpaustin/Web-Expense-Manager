import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SubscriptionsPanel from '../components/SubscriptionsPanel.jsx'
import { headline, trackPayload } from '../subscriptions.js'
import * as client from '../api/client.js'

vi.mock('../api/client.js', () => ({
  fetchSubscriptions: vi.fn(),
  createRecurring: vi.fn(),
  ignoreSubscription: vi.fn(),
  unignoreSubscription: vi.fn(),
}))

const SPOTIFY = {
  key: 'spotify', name: 'Spotify', category: 'Entertainment', currency: 'SEK', amount: '119.00', frequency: 'Monthly',
  monthly: '119.00', yearly: '1428.00', first_date: '2026-05-03', last_date: '2026-10-03', next_due: '2026-11-03',
  charges: 6, varies: false, price_change: null,
}
const NETFLIX = {
  ...SPOTIFY, key: 'netflix', name: 'Netflix', amount: '129.00', monthly: '129.00',
  price_change: { from: '109.00', to: '129.00', since: '2026-09-02', currency: 'SEK', pct_change: 18.3, direction: 'up' },
}
const DATA = {
  currency: 'SEK', count: 2, monthly_total: '248.00', yearly_total: '2976.00', unconverted_count: 0, tracked_count: 1,
  items: [NETFLIX, SPOTIFY], stopped: [{ ...SPOTIFY, key: 'oldgym', name: 'Old gym', last_date: '2026-05-01' }], ignored: [{ key: 'coffee', name: 'Coffee Bar' }],
}

describe('subscription helpers', () => {
  it('words the headline for none, none-but-tracked, one and several', () => {
    expect(headline({ count: 0, tracked_count: 0 })).toContain('No repeating charges found yet')
    expect(headline({ count: 0, tracked_count: 2 })).toContain('already in your recurring')
    expect(headline({ count: 1, monthly_total: 119, yearly_total: 1428, currency: 'SEK' })).toMatch(/^1 repeating charge you haven’t set up costs about/)
    expect(headline(DATA)).toMatch(/^2 repeating charges you haven’t set up cost about .*248\.00 a month/)
  })

  it('starts the recurring payment after the last charge so nothing is posted twice', () => {
    expect(trackPayload(SPOTIFY)).toEqual({
      item: 'Spotify', category: 'Entertainment', amount: '119.00', frequency: 'Monthly', currency: 'SEK',
      last_applied: '2026-10-03', auto_post: false,
    })
  })
})

describe('SubscriptionsPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists the subscriptions with price rises, and the stopped and hidden ones', async () => {
    client.fetchSubscriptions.mockResolvedValue(DATA)
    render(<SubscriptionsPanel />)
    expect(await screen.findByText('Netflix')).toBeTruthy()
    expect(screen.getByText('Spotify')).toBeTruthy()
    expect(screen.getByText(/Up 18.3% since/)).toBeTruthy()
    expect(screen.getByTestId('subscriptions-headline').textContent).toContain('2 repeating charges')
    expect(screen.getByText('No longer charging (1)')).toBeTruthy()
    expect(screen.getByText('Marked not a subscription (1)')).toBeTruthy()
    expect(screen.getByText('1 more already in your recurring payments.')).toBeTruthy()
  })

  it('tracks a subscription as a recurring payment and tells the page', async () => {
    client.fetchSubscriptions.mockResolvedValue(DATA)
    client.createRecurring.mockResolvedValue({})
    const onTracked = vi.fn()
    render(<SubscriptionsPanel onTracked={onTracked} />)
    await screen.findByText('Spotify')
    fireEvent.click(screen.getAllByRole('button', { name: 'Track as recurring' })[1])
    await waitFor(() => expect(client.createRecurring).toHaveBeenCalledWith(expect.objectContaining({ item: 'Spotify', last_applied: '2026-10-03' })))
    await waitFor(() => expect(onTracked).toHaveBeenCalled())
    expect(client.fetchSubscriptions).toHaveBeenCalledTimes(2) // reloaded afterwards
  })

  it('marks a name as not a subscription and can show it again', async () => {
    client.fetchSubscriptions.mockResolvedValue(DATA)
    client.ignoreSubscription.mockResolvedValue()
    client.unignoreSubscription.mockResolvedValue()
    render(<SubscriptionsPanel />)
    await screen.findByText('Netflix')
    fireEvent.click(screen.getAllByRole('button', { name: 'Not a subscription' })[0])
    await waitFor(() => expect(client.ignoreSubscription).toHaveBeenCalledWith('Netflix'))
    fireEvent.click(screen.getByRole('button', { name: 'Show again' }))
    await waitFor(() => expect(client.unignoreSubscription).toHaveBeenCalledWith('Coffee Bar'))
  })

  it('shows a calm message when nothing is found', async () => {
    client.fetchSubscriptions.mockResolvedValue({ ...DATA, count: 0, items: [], stopped: [], ignored: [], tracked_count: 0 })
    render(<SubscriptionsPanel />)
    expect((await screen.findByTestId('subscriptions-headline')).textContent).toContain('No repeating charges found yet')
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('shows a failed load, and a failed action without losing the list', async () => {
    client.fetchSubscriptions.mockRejectedValueOnce(new Error('boom'))
    const { unmount } = render(<SubscriptionsPanel />)
    expect((await screen.findByText(/Couldn’t look for subscriptions: boom/))).toBeTruthy()
    unmount()
    client.fetchSubscriptions.mockResolvedValue(DATA)
    client.createRecurring.mockRejectedValue(new Error('nope'))
    render(<SubscriptionsPanel />)
    await screen.findByText('Spotify')
    fireEvent.click(screen.getAllByRole('button', { name: 'Track as recurring' })[0])
    expect((await screen.findByRole('alert')).textContent).toBe('nope')
    expect(screen.getByText('Spotify')).toBeTruthy()
  })

  it('ignores an unexpected answer', async () => {
    client.fetchSubscriptions.mockResolvedValue({})
    render(<SubscriptionsPanel />)
    expect(await screen.findByText('Looking…')).toBeTruthy()
  })
})

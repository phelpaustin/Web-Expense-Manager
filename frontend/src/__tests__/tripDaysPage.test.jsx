import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('../api/client.js', () => ({
  fetchTripSummary: vi.fn(),
  fetchTripExpenses: vi.fn(),
  fetchTripSettlement: vi.fn(),
  fetchGroupMembers: vi.fn(),
  inviteToGroup: vi.fn(),
  removeGroupMember: vi.fn(),
  cancelGroupInvite: vi.fn(),
  changeMemberRole: vi.fn(),
  setMyMapping: vi.fn(),
  updateExpense: vi.fn(),
}))

import * as client from '../api/client.js'
import TripsPage from '../pages/TripsPage.jsx'

const TRIP = {
  id: 7, name: 'Norway in Nutshel', destination: 'Norway', start_date: '2026-06-25', end_date: '2026-06-30',
  budget: null, currency: 'SEK', status: 'Completed', member_count: 1, role: 'owner',
}
const STAY = {
  id: 1, date: '2026-06-16', category: 'Travel', shop: 'AIRBNB', description: 'AIRBNB Stay', amount: '4378.81', currency: 'SEK',
  amount_in_trip_currency: '4378.81', trip_currency: 'SEK', covers_from: null, covers_to: null,
}
const DINNER = {
  id: 2, date: '2026-06-26', category: 'Food', shop: 'Cafe', description: 'Dinner', amount: '500', currency: 'SEK',
  amount_in_trip_currency: '500', trip_currency: 'SEK', covers_from: null, covers_to: null,
}

let setError, refresh
beforeEach(() => {
  vi.clearAllMocks()
  setError = vi.fn()
  refresh = vi.fn(async () => {})
  client.fetchTripSummary.mockResolvedValue({
    unconverted_count: 0, total_spent: 4878.81, currency: 'SEK', budget: null, remaining: null, expense_count: 2, by_category: {},
  })
  client.fetchTripExpenses.mockResolvedValue([DINNER, STAY])
  client.fetchTripSettlement.mockResolvedValue({ complete: true, per_member: [] })
  client.fetchGroupMembers.mockResolvedValue([])
  client.updateExpense.mockResolvedValue({})
})

const open = async (trip = TRIP) => {
  render(<TripsPage trips={[trip]} groups={[]} onAddTrip={vi.fn()} onUpdateTrip={vi.fn()} onDeleteTrip={vi.fn()} onRefresh={refresh} onError={setError} />)
  fireEvent.click(screen.getByText(/Norway in Nutshel/))
  await screen.findByText('AIRBNB Stay')
}
const rowOf = (text) => screen.getByText(text).closest('tr')

describe('trip days on the Trips page', () => {
  it('shows which day each expense falls on in the list', async () => {
    await open()
    expect(within(rowOf('Dinner')).getByText('Day 2')).toBeTruthy()
    // the stay was paid before the trip, so it is not on a day yet
    expect(within(rowOf('AIRBNB Stay')).getByText(/16 Jun · not on a trip day/)).toBeTruthy()
  })

  it('maps a stay to days 1 to 3 and saves both ends', async () => {
    await open()
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByLabelText('Set days for AIRBNB Stay'))
    const row = rowOf('AIRBNB Stay')
    fireEvent.change(within(row).getByLabelText('From day'), { target: { value: '1' } })
    fireEvent.change(within(row).getByLabelText('To day'), { target: { value: '3' } })
    fireEvent.click(within(row).getByText('✓ Save'))
    await waitFor(() =>
      expect(client.updateExpense).toHaveBeenCalledWith(1, { covers_from: '2026-06-25', covers_to: '2026-06-27' }),
    )
    await waitFor(() => expect(client.fetchTripExpenses).toHaveBeenCalledTimes(2)) // reloaded after saving
  })

  it('the end of the range can never be before the start', async () => {
    await open()
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByLabelText('Set days for AIRBNB Stay'))
    const row = rowOf('AIRBNB Stay')
    fireEvent.change(within(row).getByLabelText('From day'), { target: { value: '4' } })
    expect(within(row).getByLabelText('To day').value).toBe('4')
    const toOptions = [...within(row).getByLabelText('To day').querySelectorAll('option')].map((o) => o.textContent)
    expect(toOptions[0]).toBe('Day 4 · 28 Jun') // nothing earlier is offered
  })

  it('"Whole trip" covers every day', async () => {
    await open()
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByLabelText('Set days for AIRBNB Stay'))
    const row = rowOf('AIRBNB Stay')
    fireEvent.click(within(row).getByText('Whole trip'))
    fireEvent.click(within(row).getByText('✓ Save'))
    await waitFor(() =>
      expect(client.updateExpense).toHaveBeenCalledWith(1, { covers_from: '2026-06-25', covers_to: '2026-06-30' }),
    )
  })

  it('clears the days of an expense that has them', async () => {
    client.fetchTripExpenses.mockResolvedValue([{ ...STAY, covers_from: '2026-06-25', covers_to: '2026-06-27' }])
    await open()
    expect(within(rowOf('AIRBNB Stay')).getByText('Day 1–3')).toBeTruthy()
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByLabelText('Set days for AIRBNB Stay'))
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByText('Clear'))
    await waitFor(() => expect(client.updateExpense).toHaveBeenCalledWith(1, { covers_from: null, covers_to: null }))
  })

  it('shows the server’s message when saving fails and keeps the editor open', async () => {
    client.updateExpense.mockRejectedValue(new Error('Not allowed'))
    await open()
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByLabelText('Set days for AIRBNB Stay'))
    fireEvent.click(within(rowOf('AIRBNB Stay')).getByText('✓ Save'))
    await waitFor(() => expect(setError).toHaveBeenCalledWith('Not allowed'))
    expect(within(rowOf('AIRBNB Stay')).getByText('✓ Save')).toBeTruthy()
  })

  it('a viewer sees the days but cannot change them', async () => {
    await open({ ...TRIP, role: 'viewer' })
    expect(within(rowOf('Dinner')).getByText('Day 2')).toBeTruthy()
    expect(screen.queryByLabelText('Set days for Dinner')).toBeNull()
  })

  it('shows the trip day by day, with a 3-day stay on each of its days', async () => {
    client.fetchTripExpenses.mockResolvedValue([DINNER, { ...STAY, covers_from: '2026-06-25', covers_to: '2026-06-27' }])
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'By day' }))
    const plan = screen.getByTestId('trip-day-plan')
    for (const label of ['Day 1 · 25 Jun', 'Day 2 · 26 Jun', 'Day 3 · 27 Jun']) {
      expect(within(plan).getByLabelText(label)).toBeTruthy()
    }
    const day2 = within(plan).getByLabelText('Day 2 · 26 Jun')
    expect(within(day2).getByText(/AIRBNB Stay/)).toBeTruthy()
    expect(within(day2).getByText(/Dinner/)).toBeTruthy()
    expect(within(day2).getByText(/1 of 3 days of/)).toBeTruthy()
    // days with nothing are folded away until asked for
    expect(within(plan).queryByLabelText('Day 4 · 28 Jun')).toBeNull()
    fireEvent.click(within(plan).getByLabelText(/Show the 3 days with nothing/))
    expect(within(plan).getByLabelText('Day 4 · 28 Jun')).toBeTruthy()
  })

  it('lists an expense paid before the trip under "Not on a trip day" until it is mapped', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'By day' }))
    const outside = screen.getByLabelText('Outside the trip dates')
    expect(within(outside).getByText(/AIRBNB Stay/)).toBeTruthy()
  })

  it('keeps the explanation in an info tip instead of showing it all the time', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'By day' }))
    const outside = screen.getByLabelText('Outside the trip dates')
    expect(within(outside).queryByText(/These fall outside the trip’s dates/)).toBeNull()
    fireEvent.click(within(outside).getByRole('button', { name: 'Why are these not on a trip day?' }))
    expect(within(outside).getByRole('tooltip').textContent).toMatch(/Days column of the list/)
  })

  it('asks for trip dates when the trip has none', async () => {
    await open({ ...TRIP, start_date: null, end_date: null })
    expect(within(rowOf('Dinner')).queryByLabelText('Set days for Dinner')).toBeNull() // nothing to choose from
    fireEvent.click(screen.getByRole('button', { name: 'By day' }))
    expect(screen.getByText(/Give the trip a start and end date/)).toBeTruthy()
  })
})

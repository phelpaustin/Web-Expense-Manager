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
  updateTrip: vi.fn(),
}))

import * as client from '../api/client.js'
import TripsPage from '../pages/TripsPage.jsx'

const TRIP = {
  id: 7, name: 'Norway in Nutshel', destination: 'Norway', start_date: '2026-06-25', end_date: '2026-10-31',
  budget: null, currency: 'SEK', status: 'Completed', member_count: 1, role: 'owner',
}

let refresh
beforeEach(() => {
  vi.clearAllMocks()
  refresh = vi.fn(async () => {})
  client.updateTrip.mockResolvedValue({})
  client.fetchTripSummary.mockResolvedValue({ unconverted_count: 0, total_spent: 0, currency: 'SEK', budget: null, remaining: null, expense_count: 0, by_category: {} })
  client.fetchTripExpenses.mockResolvedValue([])
  client.fetchTripSettlement.mockResolvedValue({ complete: true, per_member: [] })
  client.fetchGroupMembers.mockResolvedValue([])
})

const show = (trip = TRIP) =>
  render(<TripsPage trips={[trip]} groups={[]} onAddTrip={vi.fn()} onUpdateTrip={vi.fn()} onDeleteTrip={vi.fn()} onRefresh={refresh} onError={vi.fn()} />)
const openEditor = () => fireEvent.click(screen.getByLabelText('Edit trip Norway in Nutshel'))
const form = () => screen.getByRole('form', { name: 'Edit Norway in Nutshel' })
const type = (label, value) => fireEvent.change(within(form()).getByLabelText(label), { target: { value } })

describe('editing a trip', () => {
  it('opens a form filled with the trip’s details', () => {
    show()
    expect(screen.queryByRole('form')).toBeNull()
    openEditor()
    expect(within(form()).getByLabelText('Trip name').value).toBe('Norway in Nutshel')
    expect(within(form()).getByLabelText('Destination').value).toBe('Norway')
    expect(within(form()).getByLabelText('Start date').value).toBe('2026-06-25')
    expect(within(form()).getByLabelText('End date').value).toBe('2026-10-31')
    expect(within(form()).getByLabelText('Currency').value).toBe('SEK')
  })

  it('saves the changed name and dates, refreshes the trips and closes', async () => {
    show()
    openEditor()
    type('Trip name', 'Norway in a Nutshell')
    type('End date', '2026-07-02')
    fireEvent.click(within(form()).getByRole('button', { name: 'Save trip' }))
    await waitFor(() =>
      expect(client.updateTrip).toHaveBeenCalledWith(7, { name: 'Norway in a Nutshell', end_date: '2026-07-02' }),
    )
    await waitFor(() => expect(refresh).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('form')).toBeNull())
  })

  it('does not call the server when nothing changed', () => {
    show()
    openEditor()
    fireEvent.click(within(form()).getByRole('button', { name: 'Save trip' }))
    expect(client.updateTrip).not.toHaveBeenCalled()
    expect(screen.queryByRole('form')).toBeNull()
  })

  it('refuses an end date before the start without calling the server', () => {
    show()
    openEditor()
    type('Start date', '2026-07-05')
    type('End date', '2026-07-01')
    fireEvent.click(within(form()).getByRole('button', { name: 'Save trip' }))
    expect(within(form()).getByRole('alert').textContent).toMatch(/end before it starts/)
    expect(client.updateTrip).not.toHaveBeenCalled()
  })

  it('shows the server’s message and keeps the form open when saving fails', async () => {
    client.updateTrip.mockRejectedValue(new Error('Only an owner or admin can do that'))
    show()
    openEditor()
    type('Trip name', 'Renamed')
    fireEvent.click(within(form()).getByRole('button', { name: 'Save trip' }))
    expect((await within(form()).findByRole('alert')).textContent).toContain('Only an owner or admin')
    expect(within(form()).getByLabelText('Trip name').value).toBe('Renamed') // nothing lost
    expect(refresh).not.toHaveBeenCalled()
  })

  it('can clear the dates and budget', async () => {
    show({ ...TRIP, budget: '5000.00' })
    openEditor()
    type('Start date', '')
    type('End date', '')
    type('Budget (optional)', '')
    fireEvent.click(within(form()).getByRole('button', { name: 'Save trip' }))
    await waitFor(() => expect(client.updateTrip).toHaveBeenCalledWith(7, { start_date: null, end_date: null, budget: null }))
  })

  it('warns that expense days keep their real dates when the dates change', () => {
    show()
    openEditor()
    expect(within(form()).queryByText(/stay on their real dates/)).toBeNull()
    type('Start date', '2026-06-20')
    expect(within(form()).getByText(/stay on their real dates/)).toBeTruthy()
  })

  it('Cancel closes the form without saving', () => {
    show()
    openEditor()
    type('Trip name', 'Nope')
    fireEvent.click(within(form()).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('form')).toBeNull()
    expect(client.updateTrip).not.toHaveBeenCalled()
  })

  it('reloads the open trip card after saving so budget and dates are current', async () => {
    show()
    fireEvent.click(screen.getByText(/Norway in Nutshel/)) // expand
    await waitFor(() => expect(client.fetchTripSummary).toHaveBeenCalledTimes(1))
    openEditor()
    type('Trip name', 'Renamed')
    fireEvent.click(within(form()).getByRole('button', { name: 'Save trip' }))
    await waitFor(() => expect(client.fetchTripSummary).toHaveBeenCalledTimes(2))
  })

  it('shows the edit button to an admin but not to an editor or viewer', () => {
    const { unmount } = show({ ...TRIP, role: 'admin' })
    expect(screen.getByLabelText('Edit trip Norway in Nutshel')).toBeTruthy()
    unmount()
    for (const role of ['editor', 'viewer']) {
      const r = show({ ...TRIP, role })
      expect(screen.queryByLabelText('Edit trip Norway in Nutshel')).toBeNull()
      r.unmount()
    }
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('../api/client.js', () => ({
  fetchTripSummary: vi.fn(async () => ({ unconverted_count: 0, total_spent: 0, currency: 'SEK', budget: null, remaining: null, expense_count: 0, by_category: {} })),
  fetchTripExpenses: vi.fn(async () => []),
  fetchTripSettlement: vi.fn(async () => ({ complete: true, per_member: [] })),
  fetchGroupMembers: vi.fn(async () => []),
  inviteToGroup: vi.fn(),
  removeGroupMember: vi.fn(),
  cancelGroupInvite: vi.fn(),
  changeMemberRole: vi.fn(),
  setMyMapping: vi.fn(),
  updateExpense: vi.fn(),
  updateTrip: vi.fn(),
}))

import TripsPage from '../pages/TripsPage.jsx'

const TRIP = {
  id: 7, name: 'Norway', destination: 'Norway', start_date: '2026-06-25', end_date: '2026-10-31',
  budget: null, currency: 'SEK', status: 'Completed', member_count: 1, role: 'owner',
}

let onDeleteTrip
beforeEach(() => {
  onDeleteTrip = vi.fn()
})
afterEach(() => vi.restoreAllMocks())

const show = () =>
  render(<TripsPage trips={[TRIP]} groups={[]} onAddTrip={vi.fn()} onUpdateTrip={vi.fn()} onDeleteTrip={onDeleteTrip} onRefresh={vi.fn()} onError={vi.fn()} />)

describe('deleting a trip', () => {
  it('asks first and does nothing when the person says no', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    show()
    fireEvent.click(screen.getByTitle('Delete trip'))
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(onDeleteTrip).not.toHaveBeenCalled()
  })

  it('deletes once the person confirms', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    show()
    fireEvent.click(screen.getByTitle('Delete trip'))
    expect(onDeleteTrip).toHaveBeenCalledWith(7)
  })
})

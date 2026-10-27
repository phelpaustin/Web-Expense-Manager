import { describe, it, expect } from 'vitest'
import { tripFormFor, tripChanges } from '../tripEdit.js'

const TRIP = { id: 7, name: 'Norway', destination: 'Bergen', start_date: '2026-06-25', end_date: '2026-06-30', budget: '30000.00', currency: 'SEK' }

describe('tripFormFor', () => {
  it('fills the form from the trip, with blanks for what is not set', () => {
    expect(tripFormFor(TRIP)).toEqual({ name: 'Norway', destination: 'Bergen', start_date: '2026-06-25', end_date: '2026-06-30', budget: '30000', currency: 'SEK' })
    expect(tripFormFor({ id: 1, name: 'X' })).toEqual({ name: 'X', destination: '', start_date: '', end_date: '', budget: '', currency: 'SEK' })
  })
})

describe('tripChanges', () => {
  const same = () => tripFormFor(TRIP)

  it('is empty when nothing changed, even though the budget is stored as 30000.00', () => {
    expect(tripChanges(TRIP, same())).toEqual({ changes: {} })
  })

  it('sends only what changed', () => {
    expect(tripChanges(TRIP, { ...same(), name: '  Norway 2026 ', end_date: '2026-07-02' })).toEqual({
      changes: { name: 'Norway 2026', end_date: '2026-07-02' },
    })
  })

  it('clears dates, destination and budget with null or empty text', () => {
    expect(tripChanges(TRIP, { ...same(), start_date: '', end_date: '', budget: '', destination: '' })).toEqual({
      changes: { start_date: null, end_date: null, budget: null, destination: '' },
    })
  })

  it('does not report a clear for something that was already empty', () => {
    const bare = { id: 1, name: 'X', currency: 'SEK' }
    expect(tripChanges(bare, tripFormFor(bare))).toEqual({ changes: {} })
  })

  it('upper-cases the currency and sends it only when it changed', () => {
    expect(tripChanges(TRIP, { ...same(), currency: 'eur' })).toEqual({ changes: { currency: 'EUR' } })
    expect(tripChanges(TRIP, { ...same(), currency: 'sek' })).toEqual({ changes: {} })
  })

  it('refuses input the server would refuse', () => {
    expect(tripChanges(TRIP, { ...same(), name: '  ' }).error).toMatch(/name/)
    expect(tripChanges(TRIP, { ...same(), start_date: '2026-07-05', end_date: '2026-07-01' }).error).toMatch(/end before it starts/)
    expect(tripChanges(TRIP, { ...same(), budget: '0' }).error).toMatch(/budget/)
    expect(tripChanges(TRIP, { ...same(), budget: 'abc' }).error).toMatch(/budget/)
    expect(tripChanges(TRIP, { ...same(), currency: '' }).error).toMatch(/currency/)
  })

  it('allows a one-day trip and a trip with only one date', () => {
    expect(tripChanges(TRIP, { ...same(), start_date: '2026-06-25', end_date: '2026-06-25' }).error).toBeUndefined()
    expect(tripChanges(TRIP, { ...same(), end_date: '' }).changes).toEqual({ end_date: null })
  })
})

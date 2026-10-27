import { describe, it, expect } from 'vitest'
import { dayList, coveredDates, splitCents, planByDay, daysLabel, isPlaced, dayLabel } from '../tripDays.js'

const DAYS = dayList('2026-06-25', '2026-06-30') // Day 1 … Day 6

describe('dayList', () => {
  it('numbers the days of a trip from 1, both ends included', () => {
    expect(DAYS).toHaveLength(6)
    expect(DAYS[0]).toEqual({ n: 1, date: '2026-06-25' })
    expect(DAYS[5]).toEqual({ n: 6, date: '2026-06-30' })
  })
  it('crosses month and year ends', () => {
    expect(dayList('2026-12-30', '2027-01-02').map((d) => d.date)).toEqual(['2026-12-30', '2026-12-31', '2027-01-01', '2027-01-02'])
  })
  it('is empty without usable dates', () => {
    expect(dayList(null, '2026-06-30')).toEqual([])
    expect(dayList('2026-06-30', '2026-06-25')).toEqual([])
    expect(dayList('nope', 'nope')).toEqual([])
  })
  it('never makes more than a year of days', () => {
    expect(dayList('2020-01-01', '2026-01-01')).toHaveLength(366)
  })
  it('labels a day', () => {
    expect(dayLabel(DAYS[1])).toBe('Day 2 · 26 Jun')
  })
})

describe('coveredDates', () => {
  it('is the day it was paid when no days are set', () => {
    expect(coveredDates({ date: '2026-06-16' })).toEqual(['2026-06-16'])
  })
  it('is every date of the stretch when set', () => {
    expect(coveredDates({ date: '2026-06-16', covers_from: '2026-06-25', covers_to: '2026-06-27' })).toEqual([
      '2026-06-25', '2026-06-26', '2026-06-27',
    ])
  })
  it('ignores a broken range', () => {
    expect(coveredDates({ date: '2026-06-16', covers_from: '2026-06-27', covers_to: '2026-06-25' })).toEqual(['2026-06-16'])
  })
})

describe('splitCents', () => {
  it('always adds up exactly', () => {
    expect(splitCents(437881, 3)).toEqual([145961, 145960, 145960])
    expect(splitCents(437881, 3).reduce((a, b) => a + b)).toBe(437881)
    expect(splitCents(100, 1)).toEqual([100])
    expect(splitCents(1, 3)).toEqual([1, 0, 0])
  })
})

describe('planByDay', () => {
  const stay = { id: 1, description: 'Airbnb', date: '2026-06-16', amount_in_trip_currency: '4378.81', covers_from: '2026-06-25', covers_to: '2026-06-27' }
  const dinner = { id: 2, description: 'Dinner', date: '2026-06-26', amount_in_trip_currency: 500 }
  const early = { id: 3, description: 'Flight', date: '2026-06-01', amount_in_trip_currency: 1000 }
  const noRate = { id: 4, description: 'Taxi', date: '2026-06-28', amount_in_trip_currency: null }

  it('puts a 3-day stay on each of its 3 days, sharing the cost without losing a cent', () => {
    const plan = planByDay([stay], DAYS)
    expect(plan.days.map((d) => d.items.length)).toEqual([1, 1, 1, 0, 0, 0])
    expect(plan.days.slice(0, 3).reduce((sum, d) => sum + d.cents, 0)).toBe(437881)
    expect(plan.days[0].items[0]).toMatchObject({ parts: 3, spread: true, totalCents: 437881 })
  })

  it('puts an expense with no days on the day it was paid, when that is inside the trip', () => {
    const plan = planByDay([dinner], DAYS)
    expect(plan.days[1].items.map((i) => i.expense.id)).toEqual([2])
    expect(plan.days[1].cents).toBe(50000)
  })

  it('keeps an expense paid before the trip in its own bucket instead of dropping it', () => {
    const plan = planByDay([early], DAYS)
    expect(plan.days.every((d) => d.items.length === 0)).toBe(true)
    expect(plan.outside.items).toHaveLength(1)
    expect(plan.outside.cents).toBe(100000)
  })

  it('lists an expense with no exchange rate but leaves it out of the totals', () => {
    const plan = planByDay([noRate], DAYS)
    expect(plan.days[3].items[0].cents).toBeNull()
    expect(plan.days[3].cents).toBe(0)
  })

  it('every cent of the trip is accounted for across days and the outside bucket', () => {
    const all = [stay, dinner, early]
    const plan = planByDay(all, DAYS)
    const total = plan.days.reduce((s, d) => s + d.cents, 0) + plan.outside.cents
    expect(total).toBe(437881 + 50000 + 100000)
  })

  it('a stay that runs past the end of the trip sends the extra days to the outside bucket', () => {
    const late = { id: 5, date: '2026-06-29', amount_in_trip_currency: 400, covers_from: '2026-06-29', covers_to: '2026-07-02' }
    const plan = planByDay([late], DAYS)
    expect(plan.days[4].cents + plan.days[5].cents + plan.outside.cents).toBe(40000)
    expect(plan.outside.items).toHaveLength(2)
  })
})

describe('labels', () => {
  it('names the day or days', () => {
    expect(daysLabel({ date: '2026-06-26' }, DAYS)).toBe('Day 2')
    expect(daysLabel({ date: '2026-06-16', covers_from: '2026-06-25', covers_to: '2026-06-27' }, DAYS)).toBe('Day 1–3')
    expect(daysLabel({ date: '2026-06-25', covers_from: '2026-06-25', covers_to: '2026-06-25' }, DAYS)).toBe('Day 1')
  })
  it('falls back to the date when it is outside the trip', () => {
    expect(daysLabel({ date: '2026-06-16' }, DAYS)).toBe('16 Jun')
    expect(isPlaced({ date: '2026-06-16' }, DAYS)).toBe(false)
    expect(isPlaced({ date: '2026-06-26' }, DAYS)).toBe(true)
  })
})

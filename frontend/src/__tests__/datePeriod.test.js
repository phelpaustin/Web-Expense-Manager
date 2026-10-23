import { describe, it, expect } from 'vitest'
import { datesFor, lastDayOfMonth, defaultValueFor, EMPTY_DATE_FILTER, CUSTOM_RANGE, PICK_MONTH, PICK_YEAR } from '../datePeriod.js'

const TODAY = new Date(2026, 9, 23) // 23 Oct 2026
const f = (period, value = '', from = '', to = '') => datesFor({ period, value, from, to }, TODAY)

describe('datesFor', () => {
  it('has no limit by default', () => {
    expect(datesFor(EMPTY_DATE_FILTER, TODAY)).toEqual({ date_from: '', date_to: '' })
  })

  it('turns quick periods into whole calendar months', () => {
    expect(f('this_month')).toEqual({ date_from: '2026-10-01', date_to: '2026-10-31' })
    expect(f('last_month')).toEqual({ date_from: '2026-09-01', date_to: '2026-09-30' })
    expect(f('last_3')).toEqual({ date_from: '2026-08-01', date_to: '2026-10-31' })
    expect(f('last_12')).toEqual({ date_from: '2025-11-01', date_to: '2026-10-31' })
    expect(f('this_year')).toEqual({ date_from: '2026-01-01', date_to: '2026-12-31' })
    expect(f('last_year')).toEqual({ date_from: '2025-01-01', date_to: '2025-12-31' })
  })

  it('handles a particular month, including a short February', () => {
    expect(f(PICK_MONTH, '2026-02')).toEqual({ date_from: '2026-02-01', date_to: '2026-02-28' })
    expect(f(PICK_MONTH, '2024-02')).toEqual({ date_from: '2024-02-01', date_to: '2024-02-29' })
    expect(f(PICK_MONTH, '2025-12')).toEqual({ date_from: '2025-12-01', date_to: '2025-12-31' })
  })

  it('handles a particular year', () => {
    expect(f(PICK_YEAR, '2025')).toEqual({ date_from: '2025-01-01', date_to: '2025-12-31' })
  })

  it('does not filter on a half-typed month or year', () => {
    expect(f(PICK_MONTH, '')).toEqual({ date_from: '', date_to: '' })
    expect(f(PICK_YEAR, '20')).toEqual({ date_from: '', date_to: '' })
    expect(f(PICK_YEAR, '')).toEqual({ date_from: '', date_to: '' })
  })

  it('keeps a custom range as typed, open at either end', () => {
    expect(f(CUSTOM_RANGE, '', '2026-03-05', '2026-04-10')).toEqual({ date_from: '2026-03-05', date_to: '2026-04-10' })
    expect(f(CUSTOM_RANGE, '', '2026-03-05', '')).toEqual({ date_from: '2026-03-05', date_to: '' })
    expect(f(CUSTOM_RANGE, '', '', '2026-04-10')).toEqual({ date_from: '', date_to: '2026-04-10' })
  })
})

describe('helpers', () => {
  it('finds the last day of a month', () => {
    expect(lastDayOfMonth('2026-01')).toBe('2026-01-31')
    expect(lastDayOfMonth('2026-04')).toBe('2026-04-30')
  })
  it('starts a month or year picker on the current one', () => {
    expect(defaultValueFor(PICK_MONTH, TODAY)).toBe('2026-10')
    expect(defaultValueFor(PICK_YEAR, TODAY)).toBe('2026')
    expect(defaultValueFor('this_month', TODAY)).toBe('')
  })
})

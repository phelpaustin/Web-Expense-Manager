import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { barPercent, describeRow, headline, notEnoughText, rowLabel, withBars } from '../patterns.js'
import PatternsPanel from '../components/PatternsPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())

const NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const weekdays = (perDay) => NAMES.map((name, i) => ({ weekday: i, name, total: perDay[i] * 10, count: 5, days: 10, per_day: perDay[i], share_pct: 10 }))
const parts = (perDay) => ['1–7', '8–14', '15–21', '22–31'].map((label, i) => ({ label, from_day: 1, to_day: 7, total: 0, count: 1, days: 7, per_day: perDay[i], share_pct: 25 }))
const DATA = (extra = {}) => ({
  months: 6, start: '2026-04-01', end: '2026-10-16', days: 199, spent: 5000, count: 80, enough: true,
  weekdays: weekdays([10, 5, 8, 8, 20, 60, 30]), month_parts: parts([40, 20, 20, 10]),
  busiest_weekday: 'Saturday', quietest_weekday: 'Tuesday',
  weekend: { per_day: 45, weekday_per_day: 10.2, ratio: 4.4, share_pct: 60 }, currency: 'USD', unconverted_count: 0, ...extra,
})

describe('pattern helpers', () => {
  it('sizes bars against the longest, keeping a sliver for any spending', () => {
    expect(barPercent(30, 60)).toBe(50)
    expect(barPercent(60, 60)).toBe(100)
    expect(barPercent(0.1, 60)).toBe(2)
    expect(barPercent(0, 60)).toBe(0)
    expect(barPercent(5, 0)).toBe(0)
  })

  it('marks the top row of a list', () => {
    const rows = withBars(weekdays([10, 5, 8, 8, 20, 60, 30]))
    expect(rows.filter((r) => r.peak).map((r) => r.name)).toEqual(['Saturday'])
    expect(rows[5].percent).toBe(100)
    expect(rows[0].percent).toBe(17)
    expect(withBars(weekdays([0, 0, 0, 0, 0, 0, 0])).some((r) => r.peak)).toBe(false)
  })

  it('names and describes a row', () => {
    expect(rowLabel({ name: 'Monday' })).toBe('Monday')
    expect(rowLabel({ label: '22–31' })).toBe('Days 22–31')
    expect(describeRow({ name: 'Saturday', per_day: 60, share_pct: 30 }, 'weekday')).toBe('Saturday: about $60.00 a day, 30% of weekday spending.')
  })

  it('says the busiest and quietest weekday, and a big weekend gap', () => {
    expect(headline(DATA())).toBe('You spend the most on Saturdays (about $60.00 a day) and the least on Tuesdays ($5.00). Weekend days cost 4.4× a weekday.')
  })

  it('leaves out the weekend sentence when weekend and weekdays are close, and flips it when weekdays cost more', () => {
    expect(headline(DATA({ weekend: { ratio: 1.1 } }))).not.toContain('Weekend')
    expect(headline(DATA({ weekend: { ratio: 0.5 } }))).toContain('Weekdays cost 2× a weekend day.')
    expect(headline(DATA({ weekend: { ratio: null } }))).not.toContain('Week')
  })

  it('draws no conclusion without enough data', () => {
    expect(headline(DATA({ enough: false }))).toBe('')
    expect(notEnoughText({ count: 1, days: 20 })).toContain('1 expense over 20 days')
    expect(notEnoughText({ count: 5, days: 20 })).toContain('5 expenses')
  })
})

describe('PatternsPanel', () => {
  it('shows the headline and both lists', async () => {
    client.fetchPatterns.mockResolvedValue(DATA())
    render(<PatternsPanel scope="personal" refreshKey={0} />)
    await screen.findByText(/You spend the most on Saturdays/)
    expect(screen.getByLabelText('Saturday: about $60.00 a day, 10% of weekday spending.')).toBeTruthy()
    expect(screen.getByText('Days 22–31')).toBeTruthy()
    expect(screen.getAllByRole('table').length).toBe(2)
  })

  it('says there is not enough data but still shows the numbers', async () => {
    client.fetchPatterns.mockResolvedValue(DATA({ enough: false, count: 4, busiest_weekday: null, quietest_weekday: null, weekend: null }))
    render(<PatternsPanel scope="personal" refreshKey={0} />)
    await screen.findByText(/Not enough spending to see a pattern yet/)
    expect(screen.queryByText(/You spend the most/)).toBeNull()
    expect(screen.getAllByRole('table').length).toBe(2)
  })

  it('asks again when the window changes, and passes the scope', async () => {
    client.fetchPatterns.mockResolvedValue(DATA())
    render(<PatternsPanel scope="all" refreshKey={0} />)
    await screen.findByText(/You spend the most/)
    expect(client.fetchPatterns).toHaveBeenLastCalledWith({ months: 6, scope: 'all', spaceIds: undefined })
    fireEvent.change(screen.getByLabelText('Spending pattern window'), { target: { value: '12' } })
    await waitFor(() => expect(client.fetchPatterns).toHaveBeenLastCalledWith({ months: 12, scope: 'all', spaceIds: undefined }))
  })

  it('shows Loading until the data has its shape, and an error when the request fails', async () => {
    client.fetchPatterns.mockResolvedValue({})
    const { unmount } = render(<PatternsPanel refreshKey={0} />)
    expect(screen.getByText('Loading…')).toBeTruthy()
    unmount()
    client.fetchPatterns.mockRejectedValue(new Error('boom'))
    render(<PatternsPanel refreshKey={0} />)
    await waitFor(() => expect(screen.getByText(/Couldn’t load this: boom/)).toBeTruthy())
  })

  it('keeps the last data and says so when a refresh fails', async () => {
    client.fetchPatterns.mockResolvedValueOnce(DATA())
    render(<PatternsPanel refreshKey={0} />)
    await screen.findByText(/You spend the most/)
    client.fetchPatterns.mockRejectedValueOnce(new Error('offline'))
    fireEvent.change(screen.getByLabelText('Spending pattern window'), { target: { value: '3' } })
    await screen.findByText(/Couldn’t refresh: offline/)
    expect(screen.getByText(/You spend the most/)).toBeTruthy()
  })
})

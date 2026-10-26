import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { comparedWith, describeRow, partialNote, pctText } from '../periodCompare.js'
import PeriodComparePanel from '../components/PeriodComparePanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))

const row = (key, label, before, now, extra = {}) => ({
  key, label, available: before != null, before, change: before == null ? null : now - before,
  pct_change: before ? Math.round(((now - before) / before) * 1000) / 10 : null,
  direction: before == null ? null : now > before ? 'up' : now < before ? 'down' : 'flat', ...extra,
})
const DATA = {
  month: '2026-09', partial: false, through_day: null, total: 920, currency: 'SEK', unconverted_count: 0,
  months: ['2026-09', '2026-08', '2026-07'],
  comparisons: [
    row('last_month', 'Against last month', 800, 920, { month: '2026-08' }),
    row('last_year', 'Against last year', 1000, 920, { month: '2025-09' }),
    row('average', 'Against 3-month average', 920, 920, { months: ['2026-08', '2026-07', '2026-06'] }),
  ],
}

describe('period compare helpers', () => {
  it('says what a tile is measured against', () => {
    expect(comparedWith(DATA.comparisons[0])).toBe('Aug 2026')
    expect(comparedWith(DATA.comparisons[2])).toBe('Jun, Jul and Aug')
    expect(comparedWith({ key: 'average', months: ['2026-08'] })).toBe('Aug')
    expect(comparedWith({ key: 'average', months: [] })).toBe('')
  })

  it('writes percentages with a sign, and nothing when there is no base', () => {
    expect(pctText({ pct_change: 15 })).toBe('+15%')
    expect(pctText({ pct_change: -8 })).toBe('-8%')
    expect(pctText({ pct_change: 0 })).toBe('0%')
    expect(pctText({ pct_change: null })).toBe('')
  })

  it('describes each kind of row in a sentence', () => {
    expect(describeRow(DATA.comparisons[0], 920)).toBe('Against last month: up $120.00 (+15%), $920.00 against $800.00.')
    expect(describeRow(DATA.comparisons[1], 920)).toContain('down $80.00 (-8%)')
    expect(describeRow(DATA.comparisons[2], 920)).toBe('Against 3-month average: unchanged at $920.00.')
    expect(describeRow(row('last_year', 'Against last year', null, 5), 5)).toBe('Against last year: not enough history yet.')
    // a base of zero has no percentage but still has a change
    expect(describeRow(row('last_month', 'Against last month', 0, 50), 50)).toBe('Against last month: up $50.00, $50.00 against $0.00.')
  })

  it('has a note only while the month is still going', () => {
    expect(partialNote({ partial: false })).toBe('')
    expect(partialNote({ partial: true, month: '2026-10', through_day: 22 })).toBe(
      'Oct 2026 so far (to the 22nd), against the same days of each earlier month.',
    )
  })
})

describe('PeriodComparePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchPeriodCompare.mockImplementation(async () => DATA)
  })

  it('shows the three comparisons for the month the server picked', async () => {
    render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} />)
    const tiles = await screen.findAllByRole('group')
    expect(tiles).toHaveLength(3)
    expect(within(tiles[0]).getByText('+15%').className).toContain('up')
    expect(within(tiles[0]).getByText(/\$800\.00 in Aug 2026/)).toBeTruthy()
    expect(within(tiles[1]).getByText('-8%').className).toContain('down')
    expect(within(tiles[2]).getByText('No change')).toBeTruthy()
    expect(within(tiles[2]).getByText(/in Jun, Jul and Aug/)).toBeTruthy()
    expect(screen.getByText('$920.00')).toBeTruthy()
    expect(client.fetchPeriodCompare).toHaveBeenCalledWith({ month: null, scope: 'all', spaceIds: [] })
  })

  it('asks the page to change month, and reads the comparison for the month it is given', async () => {
    const onMonthChange = vi.fn()
    const { rerender } = render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} onMonthChange={onMonthChange} />)
    await screen.findAllByRole('group')
    fireEvent.change(screen.getByLabelText('Compare month'), { target: { value: '2026-07' } })
    expect(onMonthChange).toHaveBeenCalledWith('2026-07')
    rerender(<PeriodComparePanel month="2026-07" scope="all" spaceIds={[]} refreshKey={null} onMonthChange={onMonthChange} />)
    await waitFor(() => expect(client.fetchPeriodCompare).toHaveBeenLastCalledWith({ month: '2026-07', scope: 'all', spaceIds: [] }))
  })

  it('says so when there is not enough history, rather than showing zero', async () => {
    client.fetchPeriodCompare.mockImplementation(async () => ({
      ...DATA,
      comparisons: [row('last_month', 'Against last month', null, 920), DATA.comparisons[1], row('average', 'Against 3-month average', null, 920, { months: [] })],
    }))
    render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} />)
    await screen.findAllByRole('group')
    expect(screen.getAllByText('Not enough history yet')).toHaveLength(2)
  })

  it('compares a month in progress like for like and says so', async () => {
    client.fetchPeriodCompare.mockImplementation(async () => ({ ...DATA, partial: true, through_day: 22 }))
    render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/so far \(to the 22nd\), against the same days/)).toBeTruthy()
    expect(screen.getByText(/spent in Sep 2026 so far/)).toBeTruthy()
  })

  it('mentions expenses left out for lack of an exchange rate', async () => {
    client.fetchPeriodCompare.mockImplementation(async () => ({ ...DATA, unconverted_count: 2 }))
    render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/2 expenses in a currency without an exchange rate are left out/)).toBeTruthy()
  })

  it('shows the error when it cannot load', async () => {
    client.fetchPeriodCompare.mockImplementation(async () => {
      throw new Error('server down')
    })
    render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/Couldn’t load the comparison: server down/)).toBeTruthy()
  })

  it('copes with an answer that has no comparisons', async () => {
    client.fetchPeriodCompare.mockImplementation(async () => ({}))
    render(<PeriodComparePanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText('Loading…')).toBeTruthy()
  })
})

import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})
// Recharts measures real layout, which jsdom doesn't have; the chart's data is tested directly.
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>
  return { BarChart: Pass, Bar: Pass, Cell: () => null, CartesianGrid: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null, ResponsiveContainer: Pass }
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { buildWaterfall, describeChange, monthLabel, monthShort, ordinal, signedMoney } from '../categoryChange.js'
import CategoryChangePanel from '../components/CategoryChangePanel.jsx'

// Amounts are formatted in the display currency; use dollars so the expected text is short.
beforeAll(() => setDisplayCurrency('USD'))

const cat = (category, before, now, extra = {}) => ({
  category, before, now, change: now - before, pct_change: before ? Math.round(((now - before) / before) * 1000) / 10 : null,
  status: before === 0 ? 'new' : now === 0 ? 'stopped' : 'changed', ...extra,
})

const DATA = {
  month: '2026-09', compare_month: '2026-08', partial: false, through_day: null, available: true, currency: 'SEK', unconverted_count: 0,
  total: { now: 2400, before: 1200, change: 1200, pct_change: 100, direction: 'up' },
  categories: [cat('Groceries', 1000, 1800), cat('Dining', 200, 500), cat('Transport', 0, 100)],
  other: null, unchanged_count: 2, months: ['2026-07', '2026-08', '2026-09'],
}

describe('describeChange', () => {
  it('names the biggest drivers of a rise', () => {
    expect(describeChange(DATA)).toBe(
      'Spending is up $1,200.00 (+100%): Sep vs Aug. Mostly Groceries +$800.00, Dining +$300.00 and Transport +$100.00.',
    )
  })

  it('names a fall and shows an offsetting rise with its own sign', () => {
    const data = {
      ...DATA, total: { now: 1100, before: 1500, change: -400, pct_change: -26.7, direction: 'down' },
      categories: [cat('Groceries', 1000, 500), cat('Dining', 500, 600)],
    }
    expect(describeChange(data)).toBe('Spending is down $400.00 (-26.7%): Sep vs Aug. Mostly Groceries -$500.00 and Dining +$100.00.')
  })

  it('rolls the rest into "N others", with the right plural', () => {
    expect(describeChange({ ...DATA, other: { count: 3, before: 100, now: 250, change: 150 } })).toMatch(/Transport \+\$100.00 and 3 others \+\$150.00\.$/)
    expect(describeChange({ ...DATA, other: { count: 1, before: 0, now: 5, change: 5 } })).toMatch(/and 1 other \+\$5.00\.$/)
  })

  it('says the month is compared like for like while it is still in progress', () => {
    const s = describeChange({ ...DATA, month: '2026-10', compare_month: '2026-09', partial: true, through_day: 16 })
    expect(s).toMatch(/Oct so far \(to the 16th\) vs the same days of Sep/)
  })

  it('handles no change, nothing to compare with, and no data', () => {
    expect(describeChange({ ...DATA, total: { ...DATA.total, change: 0, now: 1200 } })).toBe('Spending is unchanged: Sep vs Aug.')
    expect(describeChange({ ...DATA, total: { now: 900, before: 0, change: 900, pct_change: null } })).toBe(
      '$900.00 spent in Sep, with nothing in Aug to compare with, mostly Groceries.',
    )
    expect(describeChange({ ...DATA, available: false })).toBe('No spending in Aug 2026 or Sep 2026 to compare.')
  })
})

describe('formatting helpers', () => {
  it('labels months and days', () => {
    expect([monthShort('2026-01'), monthLabel('2026-12')]).toEqual(['Jan', 'Dec 2026'])
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 30, 31].map(ordinal)).toEqual(
      ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '30th', '31st'],
    )
  })

  it('signs money', () => {
    expect([signedMoney(800), signedMoney(-300), signedMoney(0)]).toEqual(['+$800.00', '-$300.00', '$0.00'])
  })
})

describe('buildWaterfall', () => {
  it('starts at the earlier total, floats each mover from where the last ended, and ends at the later total', () => {
    const data = { ...DATA, categories: [cat('Groceries', 1000, 1800), cat('Dining', 500, 200)], total: { now: 1300, before: 1500, change: -200 }, other: null }

    const steps = buildWaterfall(data)

    expect(steps.map((s) => [s.name, s.kind, s.base, s.value])).toEqual([
      ['Aug', 'total', 0, 1500],
      ['Groceries', 'up', 1500, 800],   // 1500 -> 2300
      ['Dining', 'down', 2000, 300],    // 2300 -> 2000, drawn from 2000 up to 2300
      ['Sep', 'total', 0, 1300],
    ])
  })

  it('never starts a floating bar below zero and its last running total is the later total', () => {
    const data = {
      ...DATA, total: { now: 100, before: 1000, change: -900 },
      categories: [cat('Rent', 900, 0), cat('Food', 100, 100 + 0)].filter((c) => c.change !== 0),
      other: null,
    }

    const steps = buildWaterfall(data)

    expect(steps.every((s) => s.base >= 0)).toBe(true)
    expect(steps[1]).toMatchObject({ kind: 'down', base: 100, value: 900 })
  })

  it('adds an "others" bar and marks a month still in progress', () => {
    const data = { ...DATA, partial: true, month: '2026-10', compare_month: '2026-09', other: { count: 2, before: 10, now: 40, change: 30 } }

    const steps = buildWaterfall(data)

    expect(steps.at(-2)).toMatchObject({ name: '2 others', kind: 'up', value: 30 })
    expect(steps.at(-1).name).toBe('Oct so far')
  })
})

describe('CategoryChangePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchCategoryChange.mockImplementation(async () => DATA)
  })

  it('asks for the default month first and shows the sentence, table and unchanged count', async () => {
    render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByTestId('change-sentence')).toBeTruthy()
    expect(client.fetchCategoryChange).toHaveBeenCalledWith({ month: null, scope: 'all', spaceIds: [] })
    expect(screen.getByTestId('change-sentence').textContent).toMatch(/Spending is up \$1,200\.00/)
    expect(screen.getByRole('cell', { name: 'Groceries' })).toBeTruthy()
    expect(screen.getByText(/\+\$800\.00 \(\+80%\)/)).toBeTruthy()
    expect(screen.getByText(/2 categories unchanged\./)).toBeTruthy()
    expect(screen.getByText('(new)')).toBeTruthy() // Transport had nothing last month
  })

  it('lets the user pick another month, newest first', async () => {
    render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={null} />)
    const select = await screen.findByLabelText('Month')

    expect([...select.options].map((o) => o.value)).toEqual(['2026-09', '2026-08', '2026-07'])
    expect(select.value).toBe('2026-09')
    fireEvent.change(select, { target: { value: '2026-08' } })

    await waitFor(() => expect(client.fetchCategoryChange).toHaveBeenLastCalledWith({ month: '2026-08', scope: 'all', spaceIds: [] }))
  })

  it('keeps a quiet default month selectable even though it has no spending', async () => {
    client.fetchCategoryChange.mockImplementation(async () => ({ ...DATA, month: '2026-09', months: ['2026-07', '2026-08'] }))
    render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={null} />)

    const select = await screen.findByLabelText('Month')

    expect(select.value).toBe('2026-09')
    expect([...select.options].map((o) => o.value)).toContain('2026-09')
  })

  it('reloads when the dashboard data is refreshed', async () => {
    const { rerender } = render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={{ a: 1 }} />)
    await screen.findByTestId('change-sentence')

    rerender(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={{ a: 2 }} />)

    await waitFor(() => expect(client.fetchCategoryChange).toHaveBeenCalledTimes(2))
  })

  it('explains an empty comparison instead of drawing a chart', async () => {
    client.fetchCategoryChange.mockImplementation(async () => ({
      ...DATA, available: false, categories: [], other: null, unchanged_count: 0, total: { now: 0, before: 0, change: 0, pct_change: null, direction: 'flat' },
    }))
    render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect((await screen.findByTestId('change-sentence')).textContent).toBe('No spending in Aug 2026 or Sep 2026 to compare.')
    expect(screen.queryByTestId('change-chart')).toBeNull()
  })

  it('mentions expenses left out for lack of an exchange rate', async () => {
    client.fetchCategoryChange.mockImplementation(async () => ({ ...DATA, unconverted_count: 2 }))
    render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByText(/2 expenses in a currency without an exchange rate are left out/)).toBeTruthy()
  })

  it('shows a message when loading fails, and keeps the last answer if a refresh fails', async () => {
    client.fetchCategoryChange.mockRejectedValueOnce(new Error('boom'))
    const { rerender } = render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={1} />)
    expect(await screen.findByText(/Couldn’t load the category breakdown: boom/)).toBeTruthy()

    rerender(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={2} />)
    await screen.findByTestId('change-sentence')
    client.fetchCategoryChange.mockRejectedValueOnce(new Error('later'))
    rerender(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={3} />)

    expect(await screen.findByText(/Couldn’t refresh: later/)).toBeTruthy()
    expect(screen.getByTestId('change-sentence')).toBeTruthy()
  })

  it('ignores a slow answer that arrives after a newer choice', async () => {
    let releaseSlow
    client.fetchCategoryChange
      .mockImplementationOnce(async () => DATA)
      .mockImplementationOnce(() => new Promise((r) => { releaseSlow = () => r({ ...DATA, month: '2026-08', compare_month: '2026-07' }) }))
      .mockImplementationOnce(async () => ({ ...DATA, month: '2026-07', compare_month: '2026-06' }))
    render(<CategoryChangePanel scope="all" spaceIds={[]} refreshKey={null} />)
    const select = await screen.findByLabelText('Month')

    fireEvent.change(select, { target: { value: '2026-08' } }) // slow
    await waitFor(() => expect(client.fetchCategoryChange).toHaveBeenCalledTimes(2))
    fireEvent.change(select, { target: { value: '2026-07' } }) // newer
    await waitFor(() => expect(screen.getByLabelText('Month').value).toBe('2026-07'))
    releaseSlow()
    await new Promise((r) => setTimeout(r, 20))

    expect(screen.getByLabelText('Month').value).toBe('2026-07')
  })
})

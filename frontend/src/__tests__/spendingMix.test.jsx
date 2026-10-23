import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  mocked.fetchSpendingMix = vi.fn(async () => ({}))
  return mocked
})
// Recharts measures real layout, which jsdom doesn't have; the chart's data is tested directly.
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>
  const None = () => null
  return { BarChart: Pass, Bar: Pass, CartesianGrid: None, XAxis: None, YAxis: None, Tooltip: None, ResponsiveContainer: Pass }
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { chartRows, dayLabel, describeMix, describeOneOff, describeCommitment, describeRule, MONTH_CHOICES } from '../spendingMix.js'
import SpendingMixPanel from '../components/SpendingMixPanel.jsx'

beforeAll(() => setDisplayCurrency('USD')) // dollars keep the expected text short

const month = (m, committed, everyday, one_off, partial = false) => ({
  month: m, committed, everyday, one_off, total: committed + everyday + one_off, partial,
})

const DATA = {
  window: { from: '2026-05-01', to: '2026-10-16', months: 6 }, available: true, currency: 'SEK', unconverted_count: 0,
  months: [month('2026-08', 9000, 3000, 0), month('2026-09', 9000, 3400, 2500), month('2026-10', 9000, 800, 0, true)],
  typical: { months: 2, committed: 9000, everyday: 3200, one_off: 1250, baseline: 12200, total: 13450 },
  totals: { committed: 27000, everyday: 7200, one_off: 2500, total: 36700, committed_pct: 73.6, one_off_pct: 6.8 },
  one_off_count: 1,
  one_offs: [{ id: 1, date: '2026-09-12', description: 'Party catering', category: 'Groceries', shop: '', amount: 2500, usual: 140, ratio: 17.9, basis: 'category' }],
  committed_top: [{ template_id: 3, description: 'Rent', total: 27000, count: 3, last_date: '2026-10-01' }],
  rule: { min_samples: 8, multiple: 3, sigmas: 3 },
}

describe('helpers', () => {
  it('makes one chart bar per month and stars the month in progress', () => {
    expect(chartRows(DATA)).toEqual([
      { name: 'Aug', month: '2026-08', partial: false, committed: 9000, everyday: 3000, oneOff: 0, total: 12000 },
      { name: 'Sep', month: '2026-09', partial: false, committed: 9000, everyday: 3400, oneOff: 2500, total: 14900 },
      { name: 'Oct*', month: '2026-10', partial: true, committed: 9000, everyday: 800, oneOff: 0, total: 9800 },
    ])
  })

  it('accepts numbers sent as text', () => {
    const rows = chartRows({ months: [{ month: '2026-01', committed: '10.5', everyday: '2', one_off: '0', total: '12.5', partial: false }] })
    expect(rows[0]).toMatchObject({ committed: 10.5, everyday: 2, oneOff: 0, total: 12.5 })
  })

  it('writes dates as day and month', () => {
    expect(dayLabel('2026-01-02')).toBe('2 Jan')
    expect(dayLabel('2026-12-31')).toBe('31 Dec')
  })

  it('describes a typical month and what one-offs added', () => {
    expect(describeMix(DATA)).toBe(
      'A typical month is about $12,200.00: $9,000.00 committed and $3,200.00 everyday. One-off purchases added $2,500.00 (1 purchase).',
    )
    expect(describeMix({ ...DATA, one_off_count: 3 })).toMatch(/\(3 purchases\)\.$/)
    expect(describeMix({ ...DATA, one_off_count: 0 })).not.toMatch(/One-off/)
  })

  it('says a typical month needs more history, and handles an empty period', () => {
    expect(describeMix({ ...DATA, typical: null })).toBe(
      'So far $36,700.00: $27,000.00 committed, $7,200.00 everyday and $2,500.00 in one-offs. A typical month needs two finished months.',
    )
    expect(describeMix({ ...DATA, available: false })).toBe('No spending recorded in this period.')
  })

  it('explains why a purchase is a one-off, by category or against everything', () => {
    expect(describeOneOff(DATA.one_offs[0])).toBe('Party catering: $2,500.00 on 12 Sep, 17.9× your usual Groceries purchase ($140.00)')
    expect(describeOneOff({ ...DATA.one_offs[0], basis: 'overall' })).toMatch(/17\.9× your usual purchase \(\$140\.00\)$/)
    expect(describeOneOff({ ...DATA.one_offs[0], description: '' })).toMatch(/^Groceries: /)
  })

  it('describes a commitment with the right plural', () => {
    expect(describeCommitment(DATA.committed_top[0])).toBe('Rent: $27,000.00 (3 payments, last 1 Oct)')
    expect(describeCommitment({ ...DATA.committed_top[0], count: 1 })).toMatch(/\(1 payment, /)
  })

  it('quotes the rule the server used', () => {
    expect(describeRule(DATA.rule)).toBe(
      'A purchase counts as a one-off when it is more than 3× what you usually spend on that category, judged on your last year of purchases. A category with fewer than 8 purchases is compared with your purchases overall.',
    )
  })

  it('offers 3, 6 and 12 months', () => {
    expect(MONTH_CHOICES.map((c) => c.months)).toEqual([3, 6, 12])
  })
})

describe('SpendingMixPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchSpendingMix.mockImplementation(async () => DATA)
  })

  it('asks for 12 months by default and shows the sentence, commitments and one-offs', async () => {
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByTestId('mix-sentence')).toBeTruthy()

    expect(client.fetchSpendingMix).toHaveBeenCalledWith({ months: 12, scope: 'all', spaceIds: [] })
    expect(screen.getByTestId('mix-sentence').textContent).toMatch(/A typical month is about \$12,200\.00/)
    expect(screen.getByTestId('commitments').textContent).toMatch(/Rent: \$27,000\.00 \(3 payments/)
    expect(screen.getByTestId('one-offs').textContent).toMatch(/Party catering: \$2,500\.00 on 12 Sep/)
    expect(screen.getByText(/73\.6% of your spending was committed/)).toBeTruthy()
    expect(screen.getByTestId('mix-legend').textContent).toMatch(/Committed \(recurring\).*Everyday.*One-offs.*month in progress/)
    expect(screen.getByText(/more than 3× what you usually spend/)).toBeTruthy()
  })

  it('reloads for another number of months', async () => {
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)
    const select = await screen.findByLabelText('Months shown')

    fireEvent.change(select, { target: { value: '3' } })

    await waitFor(() => expect(client.fetchSpendingMix).toHaveBeenLastCalledWith({ months: 3, scope: 'all', spaceIds: [] }))
  })

  it('points to the Recurring page when nothing is committed yet', async () => {
    client.fetchSpendingMix.mockImplementation(async () => ({ ...DATA, committed_top: [], totals: { ...DATA.totals, committed: 0, committed_pct: 0 } }))
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByText(/Nothing counts as committed yet/)).toBeTruthy()
    expect(screen.queryByTestId('commitments')).toBeNull()
  })

  it('says how many more one-offs there are than are listed', async () => {
    client.fetchSpendingMix.mockImplementation(async () => ({ ...DATA, one_off_count: 4 }))
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByText('and 3 more.')).toBeTruthy()
  })

  it('shows no one-off list when there are none', async () => {
    client.fetchSpendingMix.mockImplementation(async () => ({ ...DATA, one_off_count: 0, one_offs: [] }))
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)

    await screen.findByTestId('mix-sentence')

    expect(screen.queryByTestId('one-offs')).toBeNull()
  })

  it('explains an empty period instead of drawing a chart', async () => {
    client.fetchSpendingMix.mockImplementation(async () => ({ ...DATA, available: false, typical: null, one_offs: [], committed_top: [] }))
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect((await screen.findByTestId('mix-sentence')).textContent).toBe('No spending recorded in this period.')
    expect(screen.queryByTestId('mix-chart')).toBeNull()
  })

  it('mentions expenses left out for lack of an exchange rate', async () => {
    client.fetchSpendingMix.mockImplementation(async () => ({ ...DATA, unconverted_count: 2 }))
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByText(/2 expenses in a currency without an exchange rate are left out/)).toBeTruthy()
  })

  it('reloads when the dashboard data is refreshed', async () => {
    const { rerender } = render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={{ a: 1 }} />)
    await screen.findByTestId('mix-sentence')

    rerender(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={{ a: 2 }} />)

    await waitFor(() => expect(client.fetchSpendingMix).toHaveBeenCalledTimes(2))
  })

  it('shows a message when loading fails, and keeps the last answer if a refresh fails', async () => {
    client.fetchSpendingMix.mockRejectedValueOnce(new Error('boom'))
    const { rerender } = render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={1} />)
    expect(await screen.findByText(/Couldn’t load the spending breakdown: boom/)).toBeTruthy()

    rerender(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={2} />)
    await screen.findByTestId('mix-sentence')
    client.fetchSpendingMix.mockRejectedValueOnce(new Error('later'))
    rerender(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={3} />)

    expect(await screen.findByText(/Couldn’t refresh: later/)).toBeTruthy()
    expect(screen.getByTestId('mix-sentence')).toBeTruthy()
  })

  it('ignores a slow answer that arrives after a newer choice', async () => {
    let releaseSlow
    client.fetchSpendingMix
      .mockImplementationOnce(async () => DATA)
      .mockImplementationOnce(() => new Promise((r) => { releaseSlow = () => r({ ...DATA, one_offs: [{ ...DATA.one_offs[0], description: 'SLOW ANSWER' }] }) }))
      .mockImplementationOnce(async () => ({ ...DATA, one_offs: [{ ...DATA.one_offs[0], description: 'NEWEST ANSWER' }] }))
    render(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={null} />)
    const select = await screen.findByLabelText('Months shown')

    fireEvent.change(select, { target: { value: '6' } }) // slow
    await waitFor(() => expect(client.fetchSpendingMix).toHaveBeenCalledTimes(2))
    fireEvent.change(select, { target: { value: '3' } }) // newer
    await screen.findByText(/NEWEST ANSWER/)
    releaseSlow()
    await new Promise((r) => setTimeout(r, 20))

    expect(screen.getByText(/NEWEST ANSWER/)).toBeTruthy()
    expect(screen.queryByText(/SLOW ANSWER/)).toBeNull()
  })
})

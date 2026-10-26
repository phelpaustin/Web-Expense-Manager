import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>
  const None = () => null
  return {
    BarChart: Pass, Bar: Pass, Cell: None, ErrorBar: None, CartesianGrid: None, XAxis: None, YAxis: None, Tooltip: None, ResponsiveContainer: Pass,
    AreaChart: Pass, Area: None, LineChart: Pass, Line: None, PieChart: Pass, Pie: Pass, Legend: None,
  }
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import MoversPanel from '../components/MoversPanel.jsx'
import InsightsPage from '../pages/InsightsPage.jsx'

beforeAll(() => setDisplayCurrency('USD'))

const r = (name, before, now, status) => ({
  name, before, now, change: now - before, pct_change: before ? Math.round(((now - before) / before) * 1000) / 10 : null,
  status: status || (before === 0 ? 'new' : now === 0 ? 'stopped' : 'changed'),
})
const DATA = {
  month: '2026-09', compare_month: '2026-08', partial: false, through_day: null, available: true, currency: 'SEK', unconverted_count: 0,
  months: ['2026-09', '2026-08'],
  categories: { rose: [r('Food', 500, 900)], fell: [r('Fun', 300, 100), r('Travel', 100, 0)], new: [r('Pets', 0, 250)] },
  shops: { rose: [], fell: [r('Cinema', 300, 100)], new: [r('Zoo', 0, 250)] },
}

describe('MoversPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchMovers.mockImplementation(async () => DATA)
  })

  it('lists what rose, fell and is new, for categories and shops', async () => {
    render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/Sep 2026 against Aug 2026/)).toBeTruthy()
    const cats = screen.getByRole('heading', { name: 'Categories' }).parentElement
    expect(within(cats).getByText('Food')).toBeTruthy()
    expect(within(cats).getByText('+$400.00 (+80%)').className).toContain('up')
    expect(within(cats).getByText('-$200.00 (-66.7%)').className).toContain('down')
    expect(within(cats).getByText('Pets')).toBeTruthy()
    expect(within(cats).getByText('$250.00')).toBeTruthy()
    const shops = screen.getByRole('heading', { name: 'Shops' }).parentElement
    expect(within(shops).getByText('Cinema')).toBeTruthy()
    expect(within(shops).getByText('Nothing rose.')).toBeTruthy()
  })

  it('says a category with nothing this month stopped, instead of showing a percentage', async () => {
    render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText('none this month (-$100.00)')).toBeTruthy()
  })

  it('asks for the month it is given, and for the default when it has none', async () => {
    const { rerender } = render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    await screen.findByText(/Sep 2026 against/)
    expect(client.fetchMovers).toHaveBeenLastCalledWith({ month: null, scope: 'all', spaceIds: [] })
    rerender(<MoversPanel month="2026-07" scope="all" spaceIds={[]} refreshKey={null} />)
    await waitFor(() => expect(client.fetchMovers).toHaveBeenLastCalledWith({ month: '2026-07', scope: 'all', spaceIds: [] }))
  })

  it('says when there is nothing earlier to compare with', async () => {
    client.fetchMovers.mockImplementation(async () => ({ ...DATA, available: false }))
    render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/Not enough history yet: there is nothing before Sep 2026/)).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Categories' })).toBeNull()
  })

  it('explains a month in progress', async () => {
    client.fetchMovers.mockImplementation(async () => ({ ...DATA, partial: true, through_day: 22 }))
    render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/to the 22nd\), against the same days/)).toBeTruthy()
    expect(screen.getByText(/Sep 2026 so far against Aug 2026/)).toBeTruthy()
  })

  it('shows the error, and copes with an answer that has no lists', async () => {
    client.fetchMovers.mockImplementation(async () => {
      throw new Error('server down')
    })
    const { unmount } = render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText(/Couldn’t load the movers: server down/)).toBeTruthy()
    unmount()
    client.fetchMovers.mockImplementation(async () => ({}))
    render(<MoversPanel scope="all" spaceIds={[]} refreshKey={null} />)
    expect(await screen.findByText('Loading…')).toBeTruthy()
  })
})

describe('Insights Overview: one month for both panels', () => {
  it('choosing a month in Compared with moves the movers to it as well', async () => {
    client.fetchMovers.mockImplementation(async () => DATA)
    client.fetchPeriodCompare.mockImplementation(async () => ({
      month: '2026-09', partial: false, through_day: null, total: 100, currency: 'SEK', unconverted_count: 0, months: ['2026-09', '2026-08'], comparisons: [],
    }))
    render(
      <InsightsPage
        trends={null} metrics={null} categories={[]} categoryMonths={[]} groups={[]} trips={[]} dashboardScope="all"
        onSetDashboardScope={vi.fn()} dashboardSpaceIds={[]} onSetDashboardSpaceIds={vi.fn()} onError={vi.fn()}
      />,
    )
    const picker = await screen.findByLabelText('Compare month')
    picker.focus()
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(picker, { target: { value: '2026-08' } })
    await waitFor(() => expect(client.fetchMovers).toHaveBeenLastCalledWith({ month: '2026-08', scope: 'all', spaceIds: [] }))
    expect(client.fetchPeriodCompare).toHaveBeenLastCalledWith({ month: '2026-08', scope: 'all', spaceIds: [] })
  })
})

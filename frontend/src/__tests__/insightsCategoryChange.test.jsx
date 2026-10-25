import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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
import InsightsPage from '../pages/InsightsPage.jsx'

const CHANGE = (month) => ({
  month, compare_month: '2026-08', partial: false, through_day: null, available: true, currency: 'SEK', unconverted_count: 0,
  total: { now: 300, before: 100, change: 200, pct_change: 200, direction: 'up' },
  categories: [{ category: 'Food', before: 100, now: 300, change: 200, pct_change: 200, status: 'changed' }],
  other: null, unchanged_count: 0, months: ['2026-08', '2026-09'],
})

function page(props = {}) {
  return (
    <InsightsPage
      initialTab="categories"
      currencies={['SEK']} displayCurrency="SEK" summary={null} budgets={[]} trends={null} categories={[]}
      onSetBudget={vi.fn()} onDeleteBudget={vi.fn()} metrics={null} periodStatus={null} budgetConfig={{ period: 'Monthly', rollover: false }}
      onSetBudgetConfig={vi.fn()} groups={[]} trips={[]} dashboardScope="all" onSetDashboardScope={vi.fn()}
      dashboardSpaceIds={[]} onSetDashboardSpaceIds={vi.fn()} {...props}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchCategoryChange.mockImplementation(async ({ month }) => CHANGE(month || '2026-09'))
})

describe('Insights: what changed', () => {
  it('shows the category change panel for the current scope', async () => {
    render(page({ dashboardScope: 'personal' }))

    expect(await screen.findByTestId('change-sentence')).toBeTruthy()
    expect(client.fetchCategoryChange).toHaveBeenCalledWith({ month: null, scope: 'personal', spaceIds: [] })
  })

  it('passes a combined selection of spaces through', async () => {
    render(page({ dashboardSpaceIds: ['personal', 3] }))

    await screen.findByTestId('change-sentence')

    expect(client.fetchCategoryChange).toHaveBeenCalledWith({ month: null, scope: 'all', spaceIds: ['personal', 3] })
  })

  it('goes back to the default month when the scope changes, rather than keeping a chosen month', async () => {
    const { rerender } = render(page({ dashboardScope: 'all' }))
    fireEvent.change(await screen.findByLabelText('Month'), { target: { value: '2026-08' } })
    await waitFor(() => expect(client.fetchCategoryChange).toHaveBeenLastCalledWith({ month: '2026-08', scope: 'all', spaceIds: [] }))

    rerender(page({ dashboardScope: 'personal' }))

    await waitFor(() => expect(client.fetchCategoryChange).toHaveBeenLastCalledWith({ month: null, scope: 'personal', spaceIds: [] }))
  })

  it('refreshes when the dashboard data is refreshed', async () => {
    const t1 = { monthly: [], change: null }
    const { rerender } = render(page({ trends: t1 }))
    await screen.findByTestId('change-sentence')
    const before = client.fetchCategoryChange.mock.calls.length

    rerender(page({ trends: { ...t1 } }))

    await waitFor(() => expect(client.fetchCategoryChange.mock.calls.length).toBe(before + 1))
  })
})

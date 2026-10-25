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

const MIX = {
  window: { from: '2025-11-01', to: '2026-10-16', months: 12 }, available: true, currency: 'SEK', unconverted_count: 0,
  months: [{ month: '2026-10', committed: 1, everyday: 2, one_off: 0, total: 3, partial: true }], typical: null,
  totals: { committed: 1, everyday: 2, one_off: 0, total: 3, committed_pct: 33.3, one_off_pct: 0 },
  one_off_count: 0, one_offs: [], committed_top: [], rule: { min_samples: 8, multiple: 3, sigmas: 3 },
}
const CHANGE = {
  month: '2026-09', compare_month: '2026-08', partial: false, through_day: null, available: false, currency: 'SEK', unconverted_count: 0,
  total: { now: 0, before: 0, change: 0, pct_change: null, direction: 'flat' }, categories: [], other: null, unchanged_count: 0, months: [],
}

function page(props = {}) {
  return (
    <InsightsPage
      initialTab="overview"
      currencies={['SEK']} displayCurrency="SEK" summary={null} budgets={[]} trends={null} categories={[]}
      onSetBudget={vi.fn()} onDeleteBudget={vi.fn()} metrics={null} periodStatus={null} budgetConfig={{ period: 'Monthly', rollover: false }}
      onSetBudgetConfig={vi.fn()} groups={[]} trips={[]} dashboardScope="all" onSetDashboardScope={vi.fn()}
      dashboardSpaceIds={[]} onSetDashboardSpaceIds={vi.fn()} {...props}
    />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchCategoryChange.mockImplementation(async () => CHANGE)
  client.fetchSpendingMix.mockImplementation(async () => MIX)
})

describe('Insights: committed vs everyday', () => {
  it('shows the panel for the current scope', async () => {
    render(page({ dashboardScope: 'personal' }))

    expect(await screen.findByTestId('mix-sentence')).toBeTruthy()
    expect(client.fetchSpendingMix).toHaveBeenCalledWith({ months: 12, scope: 'personal', spaceIds: [] })
  })

  it('passes a combined selection of spaces through', async () => {
    render(page({ dashboardSpaceIds: ['personal', 3] }))

    await screen.findByTestId('mix-sentence')

    expect(client.fetchSpendingMix).toHaveBeenCalledWith({ months: 12, scope: 'all', spaceIds: ['personal', 3] })
  })

  it('goes back to 12 months when the scope changes', async () => {
    const { rerender } = render(page({ dashboardScope: 'all' }))
    fireEvent.change(await screen.findByLabelText('Months shown'), { target: { value: '3' } })
    await waitFor(() => expect(client.fetchSpendingMix).toHaveBeenLastCalledWith({ months: 3, scope: 'all', spaceIds: [] }))

    rerender(page({ dashboardScope: 'personal' }))

    await waitFor(() => expect(client.fetchSpendingMix).toHaveBeenLastCalledWith({ months: 12, scope: 'personal', spaceIds: [] }))
  })

  it('refreshes when the dashboard data is refreshed', async () => {
    const t1 = { monthly: [], change: null, forecast_next_month: null }
    const { rerender } = render(page({ trends: t1 }))
    await screen.findByTestId('mix-sentence')
    const before = client.fetchSpendingMix.mock.calls.length

    rerender(page({ trends: { ...t1 } }))

    await waitFor(() => expect(client.fetchSpendingMix.mock.calls.length).toBe(before + 1))
  })
})

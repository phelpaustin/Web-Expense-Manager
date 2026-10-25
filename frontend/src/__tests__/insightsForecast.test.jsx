import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

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

const FORECAST = {
  available: false, reason: 'no_spending', month: '2026-10', months_available: 0, level: 80,
  requirements: { min_months: 3, months_to_test: 5, months_for_range: 7, months_for_seasons: 27 },
}
const CHANGE = {
  month: '2026-09', compare_month: '2026-08', partial: false, through_day: null, available: false, currency: 'SEK', unconverted_count: 0,
  total: { now: 0, before: 0, change: 0, pct_change: null, direction: 'flat' }, categories: [], other: null, unchanged_count: 0, months: [],
}

function page(props = {}) {
  return (
    <InsightsPage
      initialTab="forecast"
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
  client.fetchForecast.mockImplementation(async () => FORECAST)
})

describe('Insights: forecast', () => {
  it('shows the forecast panel for the current scope and combined spaces', async () => {
    render(page({ dashboardScope: 'personal', dashboardSpaceIds: ['personal', 3] }))

    expect(await screen.findByTestId('forecast-sentence')).toBeTruthy()
    expect(client.fetchForecast).toHaveBeenCalledWith({ scope: 'personal', spaceIds: ['personal', 3] })
  })

  it('refreshes when the dashboard data is refreshed', async () => {
    const t1 = { monthly: [], change: null }
    const { rerender } = render(page({ trends: t1 }))
    await screen.findByTestId('forecast-sentence')
    const before = client.fetchForecast.mock.calls.length

    rerender(page({ trends: { ...t1 } }))

    await waitFor(() => expect(client.fetchForecast.mock.calls.length).toBe(before + 1))
  })

  it('no longer shows the old one-number forecast anywhere on the page', async () => {
    const trends = {
      monthly: [{ month: '2026-08', total: 1000 }, { month: '2026-09', total: 1200 }], current_month: '2026-10', forecast_next_month: 4200,
      change: { last_month: '2026-09', previous_month: '2026-08', pct_change: 20, direction: 'up' },
    }
    render(page({ trends }))
    await screen.findByTestId('forecast-sentence')

    expect(screen.queryByText(/forecast next month/i)).toBeNull()
    expect(screen.queryByText(/forecast for/i)).toBeNull()
    expect(screen.queryByText(/4,200/)).toBeNull()
  })
})

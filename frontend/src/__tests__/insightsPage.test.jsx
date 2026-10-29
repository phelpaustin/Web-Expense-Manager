import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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
    AreaChart: Pass, Area: None, LineChart: Pass, Line: None, PieChart: Pass, Pie: Pass, Legend: None, LabelList: None,
  }
})

import * as client from '../api/client.js'
import InsightsPage from '../pages/InsightsPage.jsx'
import DashboardPage from '../pages/DashboardPage.jsx'

const SHARED = {
  groups: [{ id: 1, name: 'Home' }], trips: [], dashboardScope: 'all', onSetDashboardScope: vi.fn(),
  dashboardSpaceIds: [], onSetDashboardSpaceIds: vi.fn(), onError: vi.fn(),
}
// A complete answer: the panel formats the month, so a stub missing it would crash after the test ends.
const CHANGE = {
  month: '2026-09', compare_month: '2026-08', partial: false, through_day: null, available: false, currency: 'SEK', unconverted_count: 0,
  total: { now: 0, before: 0, change: 0, pct_change: null, direction: 'flat' }, categories: [], other: null, unchanged_count: 0, months: [],
}
const COMPARE = {
  month: '2026-09', partial: false, through_day: null, total: 0, currency: 'SEK', unconverted_count: 0, months: ['2026-09'], comparisons: [],
}
const MOVERS = {
  month: '2026-09', compare_month: '2026-08', partial: false, through_day: null, available: false, currency: 'SEK', unconverted_count: 0, months: ['2026-09'],
  categories: { rose: [], fell: [], new: [] }, shops: { rose: [], fell: [], new: [] },
}
const RECURRING = { count: 0, monthly_total: 0, yearly_total: 0, price_rises: 0, currency: 'SEK', unconverted_count: 0, items: [] }
const METRICS = {
  monthly_savings: 1500, savings_rate: 12.5, monthly_projection: 9000, volatility_cv: 18.2, daily_burn: 300, cash_flow: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchForecast.mockImplementation(async () => ({ available: false, reason: 'no_spending', month: '2026-10', months_available: 0, level: 80, requirements: {} }))
  client.fetchSpendingMix.mockImplementation(async () => ({}))
  client.fetchCategoryChange.mockImplementation(async () => CHANGE)
  client.fetchPeriodCompare.mockImplementation(async () => COMPARE)
  client.fetchMovers.mockImplementation(async () => MOVERS)
  client.fetchRecurringCosts.mockImplementation(async () => RECURRING)
})

function insights(props = {}) {
  return render(
    <MemoryRouter>
      <InsightsPage trends={null} metrics={METRICS} categories={[]} categoryMonths={[]} {...SHARED} {...props} />
    </MemoryRouter>,
  )
}

describe('Insights page', () => {
  it('has seven tabs, opening on Overview unless told otherwise', () => {
    insights()
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Overview', 'Forecast', 'Categories', 'Report', 'Members', 'Shops', 'Prices'])
    expect(screen.getByRole('tab', { name: 'Overview', selected: true })).toBeTruthy()
  })

  it('opens the Report tab, which follows the space picker like the other analysis tabs', async () => {
    client.fetchReport.mockImplementation(async () => ({
      kind: 'year', year: 2026, month: null, label: '2026', years: [2026], currency: 'SEK', unconverted_count: 0, peak: null,
      totals: { spent: 0, count: 0, income: 0, net: 0, savings_rate_pct: null, avg_per_day: 0, avg_per_month: 0 },
      previous: { label: '2025', spent: 0, count: 0, change: 0, change_pct: null },
      categories: [], periods: [], top_shops: [], largest: [], category_matrix: null,
    }))
    insights({ initialTab: 'report' })
    expect(screen.getByRole('tab', { name: 'Report', selected: true })).toBeTruthy()
    await screen.findByText('No spending recorded in 2026.')
    expect(client.fetchReport).toHaveBeenCalledWith(expect.objectContaining({ year: new Date().getFullYear(), scope: 'all' }))
    expect(screen.getByRole('button', { name: 'Download Excel' })).toBeTruthy()
  })

  it('opens the Members tab, which follows the space picker', async () => {
    client.fetchMembers.mockImplementation(async () => ({
      date_from: null, date_to: null, member_count: 0, total: 0, count: 0, members: [], categories: [], months: [], months_total: 0,
      spaces: [], currency: 'SEK', unconverted_count: 0,
    }))
    insights({ initialTab: 'members' })
    expect(screen.getByRole('tab', { name: 'Members', selected: true })).toBeTruthy()
    await screen.findByText('Spending by member needs a shared space with other people in it.')
    expect(client.fetchMembers).toHaveBeenCalledWith(expect.objectContaining({ scope: 'all' }))
  })

  it('opens on the tab asked for, and falls back to Overview for an unknown name', () => {
    const { unmount } = insights({ initialTab: 'categories' })
    expect(screen.getByRole('tab', { name: 'Categories', selected: true })).toBeTruthy()
    unmount()
    insights({ initialTab: 'nonsense' })
    expect(screen.getByRole('tab', { name: 'Overview', selected: true })).toBeTruthy()
  })

  it('shows the volatility that left the Dashboard on the Overview tab', () => {
    insights()
    expect(screen.getByText('Spend volatility')).toBeTruthy()
    expect(screen.getByText('18.2%')).toBeTruthy()
  })

  it('offers the space picker on the analysis tabs but not on Shops and Prices', async () => {
    insights()
    expect(screen.getByTitle(/Show data for personal expenses only/)).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: 'Shops' }))
    expect(screen.queryByTitle(/Show data for personal expenses only/)).toBeNull()
    expect(await screen.findByRole('heading', { level: 1, name: /Insights/ })).toBeTruthy()
    // Shops brings its own title only when it is a page of its own
    expect(screen.queryByRole('heading', { name: /🏪 Shops/ })).toBeNull()
  })

  it('shows the category breakdown with its period picker on the Categories tab', () => {
    insights({ initialTab: 'categories', categories: [{ category: 'Food', total: 100 }] })
    expect(screen.getByTestId('category-period')).toBeTruthy()
    expect(screen.getByRole('combobox', { name: 'Category breakdown period' })).toBeTruthy()
  })

  it('shows the forecast on its own tab, not on the Overview', async () => {
    insights()
    expect(client.fetchForecast).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('tab', { name: 'Forecast' }))
    expect(await screen.findByTestId('forecast-sentence')).toBeTruthy()
  })
})

describe('Dashboard after the split', () => {
  function dashboard(props = {}) {
    return render(
      <MemoryRouter>
        <DashboardPage
          currencies={['SEK']} displayCurrency="SEK" budgets={[]} trends={{ monthly: [], change: null }} periodStatus={null}
          summary={{ total: 5000, count: 12, by_category: { Food: 1 }, unconverted_count: 0 }} metrics={METRICS}
          budgetConfig={{ period: 'Monthly', rollover: false }} onSetBudget={vi.fn()} onDeleteBudget={vi.fn()} onSetBudgetConfig={vi.fn()}
          {...SHARED} {...props}
        />
      </MemoryRouter>,
    )
  }

  it('keeps four headline numbers and drops the analysis', () => {
    dashboard()
    for (const label of ['Total spent', 'Net this month', 'Savings rate', 'Projected spend']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    for (const gone of ['Transactions', 'Categories', 'Spend volatility', /Cash flow/, /Category breakdown/]) {
      expect(screen.queryByText(gone)).toBeNull()
    }
    expect(client.fetchForecast).not.toHaveBeenCalled()
    expect(client.fetchCategoryChange).not.toHaveBeenCalled()
    expect(client.fetchSpendingMix).not.toHaveBeenCalled()
  })

  it('links the trend to Insights', () => {
    dashboard()
    expect(screen.getByRole('link', { name: 'More in Insights' }).getAttribute('href')).toBe('/insights')
  })
})

describe('Insights tabs and the address', () => {
  it('tells the parent when a tab is chosen', () => {
    const onTabChange = vi.fn()
    insights({ onTabChange })
    fireEvent.click(screen.getByRole('tab', { name: 'Shops' }))
    expect(onTabChange).toHaveBeenCalledWith('shops')
    expect(screen.getByRole('tab', { name: 'Shops' }).getAttribute('aria-selected')).toBe('true')
  })

  it('follows a new initialTab without being remounted', () => {
    const { rerender } = insights({ initialTab: 'overview' })
    rerender(<MemoryRouter><InsightsPage trends={null} metrics={METRICS} categories={[]} categoryMonths={[]} {...SHARED} initialTab="report" /></MemoryRouter>)
    expect(screen.getByRole('tab', { name: 'Report' }).getAttribute('aria-selected')).toBe('true')
  })
})

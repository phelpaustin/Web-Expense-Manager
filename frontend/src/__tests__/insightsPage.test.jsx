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
    AreaChart: Pass, Area: None, LineChart: Pass, Line: None, PieChart: Pass, Pie: Pass, Legend: None,
  }
})

import * as client from '../api/client.js'
import InsightsPage from '../pages/InsightsPage.jsx'
import DashboardPage from '../pages/DashboardPage.jsx'

const SHARED = {
  groups: [{ id: 1, name: 'Home' }], trips: [], dashboardScope: 'all', onSetDashboardScope: vi.fn(),
  dashboardSpaceIds: [], onSetDashboardSpaceIds: vi.fn(), onError: vi.fn(),
}
const METRICS = {
  monthly_savings: 1500, savings_rate: 12.5, monthly_projection: 9000, volatility_cv: 18.2, daily_burn: 300, cash_flow: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchForecast.mockImplementation(async () => ({ available: false, reason: 'no_spending', month: '2026-10', months_available: 0, level: 80, requirements: {} }))
  client.fetchSpendingMix.mockImplementation(async () => ({}))
  client.fetchCategoryChange.mockImplementation(async () => ({ available: false, categories: [], months: [], total: {} }))
})

function insights(props = {}) {
  return render(<InsightsPage trends={null} metrics={METRICS} categories={[]} categoryMonths={[]} {...SHARED} {...props} />)
}

describe('Insights page', () => {
  it('has the five tabs, opening on Overview unless told otherwise', () => {
    insights()
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Overview', 'Forecast', 'Categories', 'Shops', 'Prices'])
    expect(screen.getByRole('tab', { name: 'Overview', selected: true })).toBeTruthy()
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

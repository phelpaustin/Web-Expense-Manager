import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, within, renderHook, act } from '@testing-library/react'

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
import { levelLabel, sinceLabel, percent, describeRisk, headline, describeMethod, periodUnit } from '../budgetRisk.js'
import BudgetRiskPanel from '../components/BudgetRiskPanel.jsx'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from '../pages/DashboardPage.jsx'
import { useAppData } from '../hooks/useAppData.js'

beforeAll(() => setDisplayCurrency('USD')) // dollars keep the expected text short

const item = (over = {}) => ({
  category: 'Groceries', is_total: false, period: 'Monthly', label: 'October 2026', limit: 1000, spent: 600, remaining: 400, pct: 60,
  days_remaining: 10, align: 'month', anchor: 21, available: true, reason: null, probability: 92.9, level: 'very_likely',
  samples: 6, exceeded: 6, typical_remaining: 500, ...over,
})

const RISK = { today: '2026-10-21', has_budgets: true, min_periods: 4, alert_threshold: 75, items: [item()] }

describe('sentences', () => {
  it('gives the room left, the evidence, and what is typical', () => {
    expect(describeRisk(item())).toBe(
      '$400.00 left with 10 days to go. In 6 of the last 6 months, spending after the 21st went past that. Typically about $500.00 more is spent.',
    )
  })

  it('uses singular words for one day or one period', () => {
    expect(describeRisk(item({ days_remaining: 1, samples: 1, exceeded: 1 }))).toMatch(/with 1 day to go\. In 1 of the last 1 month, /)
  })

  it('talks about weeks and weekdays for a weekly budget', () => {
    const weekly = item({ align: 'week', anchor: 2, samples: 12, exceeded: 3, days_remaining: 4, is_total: true, category: 'Total', period: 'Weekly' })
    expect(describeRisk(weekly)).toMatch(/with 4 days to go\. In 3 of the last 12 weeks, spending after Wednesday went past that\./)
    expect(sinceLabel(weekly)).toBe('Wednesday')
    expect(periodUnit(weekly)).toBe('week')
  })

  it('leaves out the typical amount when nothing more is usually spent', () => {
    expect(describeRisk(item({ typical_remaining: 0 }))).not.toMatch(/Typically/)
  })

  it('says how far over when already over', () => {
    expect(describeRisk(item({ level: 'over', remaining: -160, probability: 100 }))).toBe('Over budget by $160.00.')
  })

  it('says what is missing when there is not enough history', () => {
    expect(describeRisk(item({ available: false, level: null, probability: null, samples: 3, reason: 'not_enough_history' }))).toBe(
      'Needs 4 earlier months of history to estimate this (3 so far).',
    )
  })

  it('says the period is ending when it ends today within budget', () => {
    expect(describeRisk(item({ days_remaining: 0, probability: 0, level: 'unlikely' }))).toBe('The month ends today and you are within budget.')
  })

  it('labels the levels and rounds the chance to a whole percent', () => {
    expect(['over', 'very_likely', 'likely', 'possible', 'unlikely', null].map(levelLabel)).toEqual(
      ['Already over', 'Very likely', 'Likely', 'Possible', 'Unlikely', 'Not estimated'],
    )
    expect(percent({ probability: 92.9 })).toBe('93%')
    expect(percent({ probability: 5.6 })).toBe('6%')
  })

  it('summarises the whole picture in one line', () => {
    const base = { alert_threshold: 75, items: [] }
    expect(headline({ ...base, items: [item({ probability: 10, level: 'unlikely' })] })).toBe('No budget looks likely to be exceeded.')
    expect(headline({ ...base, items: [item(), item({ category: 'Fun', probability: 80 })] })).toBe('2 budgets very likely to be exceeded.')
    expect(headline({ ...base, items: [item({ level: 'over', probability: 100 }), item({ category: 'B' })] })).toBe(
      '1 budget already over, 1 budget very likely to be exceeded.',
    )
    expect(headline({ ...base, items: [item({ available: false, probability: null, level: null })] })).toBe(
      'Not enough history yet to estimate the chance of going over.',
    )
  })

  it('explains what the numbers are based on', () => {
    expect(describeMethod(RISK)).toMatch(/needs 4 earlier periods, and it is never 0% or 100%.*You are warned when the chance reaches 75%\./)
  })
})

describe('BudgetRiskPanel', () => {
  it('shows each budget with its chance, level and reason', () => {
    render(<BudgetRiskPanel risk={{ ...RISK, items: [item(), item({ category: 'Total', is_total: true, probability: 5.6, level: 'unlikely', remaining: 800, spent: 10200, limit: 11000 })] }} />)

    expect(screen.getByTestId('risk-headline').textContent).toBe('1 budget very likely to be exceeded.')
    const rows = screen.getAllByTestId('risk-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Groceries')).toBeTruthy()
    expect(within(rows[0]).getByText('93% · Very likely')).toBeTruthy()
    expect(within(rows[0]).getByText(/\$600\.00 of \$1,000\.00/)).toBeTruthy()
    expect(within(rows[1]).getByText('Overall (monthly)')).toBeTruthy()
    expect(within(rows[1]).getByText('6% · Unlikely')).toBeTruthy()
  })

  it('shows no chance for a budget that cannot be estimated yet, but says why', () => {
    render(<BudgetRiskPanel risk={{ ...RISK, items: [item({ category: 'Gifts', available: false, probability: null, level: null, samples: 2, reason: 'not_enough_history' })] }} />)

    expect(screen.getByText('Needs 4 earlier months of history to estimate this (2 so far).')).toBeTruthy()
    expect(screen.queryByText(/%\s·/)).toBeNull()
  })

  it('colours the chance by how serious it is', () => {
    render(<BudgetRiskPanel risk={{ ...RISK, items: [item(), item({ category: 'Safe', probability: 5, level: 'unlikely' })] }} />)

    expect(screen.getByText('93% · Very likely').style.color).toBe('rgb(249, 115, 22)')
    expect(screen.getByText('5% · Unlikely').style.color).toBe('rgb(16, 185, 129)')
  })

  it('shows nothing until there is a budget to talk about', () => {
    const { container, rerender } = render(<BudgetRiskPanel risk={null} />)
    expect(container.textContent).toBe('')
    rerender(<BudgetRiskPanel risk={{ ...RISK, has_budgets: false, items: [] }} />)
    expect(container.textContent).toBe('')
  })
})

function page(props = {}) {
  return (
    <MemoryRouter>
      <DashboardPage
        currencies={['SEK']} displayCurrency="SEK" summary={null} budgets={[]} trends={null}
        onSetBudget={vi.fn()} onDeleteBudget={vi.fn()} metrics={null} periodStatus={null} budgetConfig={{ period: 'Monthly', rollover: false }}
        onSetBudgetConfig={vi.fn()} groups={[]} trips={[]} dashboardScope="all" onSetDashboardScope={vi.fn()}
        dashboardSpaceIds={[]} onSetDashboardSpaceIds={vi.fn()} {...props}
      />
    </MemoryRouter>
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows the chance panel under the budget bars when there is risk data', () => {
    render(page({ budgetRisk: RISK }))

    expect(screen.getByText('🎲 Chance of going over')).toBeTruthy()
    expect(screen.getByTestId('risk-headline')).toBeTruthy()
  })

  it('leaves it out without risk data', () => {
    render(page({ budgetRisk: null }))
    expect(screen.queryByText('🎲 Chance of going over')).toBeNull()
  })

  it('puts it after the budget status section and before the spending trend', () => {
    const { container } = render(page({ budgetRisk: RISK, budgets: [{ category: 'Groceries', budget: 1000, spent: 600, remaining: 400, pct: 60, status: 'ok' }] }))
    const text = container.textContent
    expect(text.indexOf('Budget status')).toBeLessThan(text.indexOf('Chance of going over'))
  })
})

describe('useAppData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchDashboard.mockResolvedValue({
      summary: null, trends: null, categories: [], budgets: [], metrics: null, period_status: null, alerts: [], budget_risk: RISK,
    })
  })

  it('keeps the chance data from the dashboard payload, and clears it on sign-out', async () => {
    const { result } = renderHook(() => useAppData())
    expect(result.current.budgetRisk).toBeNull()

    await act(async () => {
      await result.current.loadAll()
    })
    expect(result.current.budgetRisk).toEqual(RISK)

    act(() => result.current.resetData())
    expect(result.current.budgetRisk).toBeNull()
  })

  it('copes with an older server that does not send it', async () => {
    client.fetchDashboard.mockResolvedValue({ summary: null, trends: null, categories: [], budgets: [], metrics: null, period_status: null, alerts: [] })
    const { result } = renderHook(() => useAppData())

    await act(async () => {
      await result.current.loadAll()
    })

    expect(result.current.budgetRisk).toBeNull()
  })
})

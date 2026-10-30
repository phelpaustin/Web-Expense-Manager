import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import { monthlyEquivalent } from '../recurringCosts.js'
import RecurringPage from '../pages/RecurringPage.jsx'

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())

const tpl = (id, item, amount, frequency) => ({ id, item, category: 'Bills', frequency, amount, currency: 'USD', last_applied: null, due: false, auto_post: false })
const TEMPLATES = [tpl(1, 'Netflix', 12, 'Monthly'), tpl(2, 'Insurance', 120, 'Yearly'), tpl(3, 'Gym', 30, 'Quarterly')]
const COSTS = {
  count: 3, monthly_total: 32, yearly_total: 384, price_rises: 0,
  items: [
    { id: 1, item: 'Netflix', frequency: 'Monthly', monthly: 12, yearly: 144 },
    { id: 2, item: 'Insurance', frequency: 'Yearly', monthly: 10, yearly: 120 },
    { id: 3, item: 'Gym', frequency: 'Quarterly', monthly: 10, yearly: 120 },
  ],
}

function page(recurring = TEMPLATES) {
  return (
    <RecurringPage
      recurring={recurring}
      recurringForm={{ item: '', category: '', amount: '', currency: '', frequency: 'Monthly', auto_post: false }}
      setRecurringForm={vi.fn()}
      onAdd={vi.fn()} onApply={vi.fn()} onApplyDue={vi.fn()} onDelete={vi.fn()} onUpdate={vi.fn()} onBackfill={vi.fn()}
      currencies={['USD']} baseCurrency="USD"
    />
  )
}

describe('monthlyEquivalent', () => {
  it('says what a non-monthly payment comes to a month, and nothing for a monthly one or an unknown one', () => {
    expect(monthlyEquivalent({ frequency: 'Yearly' }, { monthly: 10 })).toBe('about $10.00 a month')
    expect(monthlyEquivalent({ frequency: 'Monthly' }, { monthly: 12 })).toBe('')
    expect(monthlyEquivalent({ frequency: 'Yearly' }, undefined)).toBe('')
    expect(monthlyEquivalent(undefined, { monthly: 1 })).toBe('')
  })
})

describe('Recurring page costs', () => {
  it('says what everything costs a month, and what each non-monthly payment comes to', async () => {
    client.fetchRecurringCosts.mockResolvedValue(COSTS)
    render(page())
    const line = await screen.findByTestId('recurring-cost-line')
    expect(line.textContent).toBe('3 recurring payments cost about $32.00 a month ($384.00 a year).')
    expect(screen.getAllByText('about $10.00 a month')).toHaveLength(2)
    expect(screen.queryByText('about $12.00 a month')).toBeNull()
  })

  it('shows no cost line without templates', async () => {
    client.fetchRecurringCosts.mockResolvedValue({ ...COSTS, count: 0, items: [], monthly_total: 0, yearly_total: 0 })
    render(page([]))
    await waitFor(() => expect(client.fetchRecurringCosts).toHaveBeenCalled())
    expect(screen.queryByTestId('recurring-cost-line')).toBeNull()
  })

  it('still shows the page when the costs cannot be loaded', async () => {
    client.fetchRecurringCosts.mockRejectedValue(new Error('boom'))
    render(page())
    await waitFor(() => expect(client.fetchRecurringCosts).toHaveBeenCalled())
    expect(screen.getByText('Netflix')).toBeTruthy()
    expect(screen.queryByTestId('recurring-cost-line')).toBeNull()
  })

  it('ignores a malformed answer', async () => {
    client.fetchRecurringCosts.mockResolvedValue({})
    render(page())
    await waitFor(() => expect(client.fetchRecurringCosts).toHaveBeenCalled())
    expect(screen.queryByTestId('recurring-cost-line')).toBeNull()
    expect(screen.queryByText(/a month$/)).toBeNull()
  })

  it('asks again when the list of templates changes', async () => {
    client.fetchRecurringCosts.mockResolvedValue(COSTS)
    const { rerender } = render(page())
    await screen.findByTestId('recurring-cost-line')
    client.fetchRecurringCosts.mockResolvedValue({ ...COSTS, count: 4, monthly_total: 42, yearly_total: 504 })
    rerender(page([...TEMPLATES, tpl(4, 'Music', 10, 'Monthly')]))
    await waitFor(() => expect(screen.getByTestId('recurring-cost-line').textContent).toContain('4 recurring payments cost about $42.00'))
    expect(client.fetchRecurringCosts).toHaveBeenCalledTimes(2)
  })

  it('does not let a slow old answer replace a newer one', async () => {
    let releaseOld
    client.fetchRecurringCosts.mockImplementationOnce(() => new Promise((r) => { releaseOld = () => r(COSTS) }))
    const { rerender } = render(page())
    client.fetchRecurringCosts.mockResolvedValue({ ...COSTS, count: 4, monthly_total: 42, yearly_total: 504 })
    rerender(page([...TEMPLATES, tpl(4, 'Music', 10, 'Monthly')]))
    await waitFor(() => expect(screen.getByTestId('recurring-cost-line').textContent).toContain('$42.00'))
    releaseOld()
    await Promise.resolve()
    expect(screen.getByTestId('recurring-cost-line').textContent).toContain('$42.00')
  })
})

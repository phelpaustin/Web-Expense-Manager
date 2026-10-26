import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'

vi.mock('../api/client.js', () => ({
  fetchExpenses: vi.fn(),
  fetchIncome: vi.fn(),
}))

import { fetchExpenses, fetchIncome } from '../api/client.js'
import MonthDetailDialog from '../components/MonthDetailDialog.jsx'

const EXPENSE = { id: 1, date: '2025-01-10', description: 'Milk', shop: 'ICA', category: 'Food', amount: '25.50', currency: 'SEK' }
const INCOME = [
  { id: 1, date: '2025-01-25', amount: '40000', source: 'Salary', note: '', currency: 'SEK' },
  { id: 2, date: '2025-02-25', amount: '41000', source: 'Salary', note: '', currency: 'SEK' },
]

beforeEach(() => {
  vi.clearAllMocks()
  fetchExpenses.mockResolvedValue({ items: [EXPENSE], total: 1 })
  fetchIncome.mockResolvedValue(INCOME)
})

describe('MonthDetailDialog', () => {
  it('lists that month’s expenses and income', async () => {
    render(<MonthDetailDialog month="2025-01" scope="all" spaceIds={[]} onClose={() => {}} onChangeMonth={() => {}} />)
    const expenses = await screen.findByTestId('month-expenses')
    expect(within(expenses).getByText('Milk')).toBeTruthy()
    const income = screen.getByTestId('month-income')
    expect(within(income).getAllByText('Salary')).toHaveLength(1) // February's salary is left out
    expect(fetchExpenses).toHaveBeenCalledWith(
      expect.objectContaining({ date_from: '2025-01-01', date_to: '2025-01-31', page: 1 }),
    )
  })

  it('skips income for a shared space and says why', async () => {
    render(<MonthDetailDialog month="2025-01" scope="3" spaceIds={[]} onClose={() => {}} onChangeMonth={() => {}} />)
    await screen.findByTestId('month-expenses')
    expect(fetchIncome).not.toHaveBeenCalled()
    expect(screen.getByText(/Income is personal/)).toBeTruthy()
  })

  it('moves between months and closes on Escape', async () => {
    const onChange = vi.fn()
    const onClose = vi.fn()
    render(<MonthDetailDialog month="2025-01" scope="all" spaceIds={[]} onClose={onClose} onChangeMonth={onChange} />)
    await screen.findByTestId('month-expenses')
    fireEvent.click(screen.getByLabelText('Previous month'))
    expect(onChange).toHaveBeenCalledWith('2024-12')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('shows an error when loading fails', async () => {
    fetchExpenses.mockRejectedValue(new Error('boom'))
    render(<MonthDetailDialog month="2025-01" scope="all" spaceIds={[]} onClose={() => {}} onChangeMonth={() => {}} />)
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('boom'))
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'

vi.mock('../api/client.js', () => ({
  fetchExpenses: vi.fn(),
  fetchIncome: vi.fn(),
  updateExpense: vi.fn(),
  deleteExpense: vi.fn(),
}))

import { fetchExpenses, fetchIncome, updateExpense, deleteExpense } from '../api/client.js'
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
  updateExpense.mockResolvedValue({})
  deleteExpense.mockResolvedValue({})
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

  describe('editing and deleting', () => {
    const OPTIONS = { categories: ['Food'], shops: ['ICA'], currencies: ['SEK', 'EUR'] }
    const open = (props = {}) =>
      render(
        <MonthDetailDialog
          month="2025-01" scope="all" spaceIds={[]} options={OPTIONS} onClose={() => {}} onChangeMonth={() => {}} {...props}
        />,
      )

    it('saves only the changed field, reloads the month and tells the page', async () => {
      const onChanged = vi.fn()
      open({ onChanged })
      fireEvent.click(await screen.findByLabelText('Edit Milk'))
      fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '30' } })
      fireEvent.click(screen.getByText('✓ Save'))
      await waitFor(() => expect(updateExpense).toHaveBeenCalledWith(1, { amount: 30 }))
      await waitFor(() => expect(onChanged).toHaveBeenCalled())
      await waitFor(() => expect(fetchExpenses).toHaveBeenCalledTimes(2)) // the month was loaded again
      expect(screen.queryByText('✓ Save')).toBeNull()
    })

    it('does not call the server when nothing changed', async () => {
      open()
      fireEvent.click(await screen.findByLabelText('Edit Milk'))
      fireEvent.click(screen.getByText('✓ Save'))
      expect(updateExpense).not.toHaveBeenCalled()
      expect(screen.queryByText('✓ Save')).toBeNull()
    })

    it('refuses a zero amount and keeps the edit open', async () => {
      open()
      fireEvent.click(await screen.findByLabelText('Edit Milk'))
      fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '0' } })
      fireEvent.click(screen.getByText('✓ Save'))
      expect((await screen.findByRole('alert')).textContent).toMatch(/amount/)
      expect(updateExpense).not.toHaveBeenCalled()
      expect(screen.getByText('✓ Save')).toBeTruthy()
    })

    it('shows the server’s message when saving fails', async () => {
      updateExpense.mockRejectedValue(new Error('Not allowed'))
      open()
      fireEvent.click(await screen.findByLabelText('Edit Milk'))
      fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '30' } })
      fireEvent.click(screen.getByText('✓ Save'))
      expect((await screen.findByRole('alert')).textContent).toContain('Not allowed')
    })

    it('Escape cancels the edit first and only then closes the window', async () => {
      const onClose = vi.fn()
      open({ onClose })
      fireEvent.click(await screen.findByLabelText('Edit Milk'))
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(screen.queryByText('✓ Save')).toBeNull()
      expect(onClose).not.toHaveBeenCalled()
      fireEvent.keyDown(document, { key: 'Escape' })
      expect(onClose).toHaveBeenCalled()
    })

    it('asks before deleting, then deletes and reloads', async () => {
      const onChanged = vi.fn()
      open({ onChanged })
      fireEvent.click(await screen.findByLabelText('Delete Milk'))
      expect(deleteExpense).not.toHaveBeenCalled()
      fireEvent.click(screen.getByText('Yes'))
      await waitFor(() => expect(deleteExpense).toHaveBeenCalledWith(1))
      await waitFor(() => expect(onChanged).toHaveBeenCalled())
    })

    it('backs out of a delete with No', async () => {
      open()
      fireEvent.click(await screen.findByLabelText('Delete Milk'))
      fireEvent.click(screen.getByText('No'))
      expect(deleteExpense).not.toHaveBeenCalled()
      expect(screen.getByLabelText('Delete Milk')).toBeTruthy()
    })

    it('offers no edit or delete for an expense in a space where you are a viewer', async () => {
      fetchExpenses.mockResolvedValue({ items: [{ ...EXPENSE, group_id: 3 }], total: 1 })
      open({ groups: [{ id: 3, role: 'viewer' }] })
      await screen.findByTestId('month-expenses')
      expect(screen.queryByLabelText('Edit Milk')).toBeNull()
      expect(screen.queryByLabelText('Delete Milk')).toBeNull()
    })
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { useIncomeHandlers } from '../hooks/useIncomeHandlers.js'

beforeEach(() => vi.clearAllMocks())

const row = { id: 7, date: '2026-10-25', source: 'Salary', note: 'Oct', amount: '3000.00', currency: 'SEK' }
const submit = { preventDefault() {} }

describe('editing an income entry', () => {
  it('fills the form from the row and saves with PUT, not POST', async () => {
    const loadAll = vi.fn(async () => {})
    const { result } = renderHook(() => useIncomeHandlers(loadAll, vi.fn()))
    act(() => result.current.startEditIncome(row))
    expect(result.current.editingIncomeId).toBe(7)
    expect(result.current.incomeForm).toMatchObject({ source: 'Salary', amount: '3000.00', currency: 'SEK' })

    act(() => result.current.setIncomeForm({ ...result.current.incomeForm, amount: '3200' }))
    await act(async () => { await result.current.handleAddIncome(submit) })

    expect(client.updateIncome).toHaveBeenCalledWith(7, expect.objectContaining({ amount: 3200, source: 'Salary', date: '2026-10-25' }))
    expect(client.createIncome).not.toHaveBeenCalled()
    expect(loadAll).toHaveBeenCalled()
    expect(result.current.editingIncomeId).toBeNull()
    expect(result.current.incomeForm.source).toBe('')
  })

  it('cancel clears the form and the next save adds a new entry', async () => {
    const { result } = renderHook(() => useIncomeHandlers(vi.fn(async () => {}), vi.fn()))
    act(() => result.current.startEditIncome(row))
    act(() => result.current.cancelEditIncome())
    expect(result.current.editingIncomeId).toBeNull()
    act(() => result.current.setIncomeForm({ date: '2026-11-01', source: 'Gift', note: '', amount: '50', currency: '' }))
    await act(async () => { await result.current.handleAddIncome(submit) })
    expect(client.createIncome).toHaveBeenCalled()
    expect(client.updateIncome).not.toHaveBeenCalled()
  })

  it('keeps the entry in edit mode when saving fails', async () => {
    client.updateIncome.mockRejectedValueOnce(new Error('boom'))
    const setError = vi.fn()
    const { result } = renderHook(() => useIncomeHandlers(vi.fn(async () => {}), setError))
    act(() => result.current.startEditIncome(row))
    await act(async () => { await result.current.handleAddIncome(submit) })
    expect(setError).toHaveBeenCalledWith('boom')
    expect(result.current.editingIncomeId).toBe(7)
  })

  it('deleting the entry being edited leaves edit mode', async () => {
    const { result } = renderHook(() => useIncomeHandlers(vi.fn(async () => {}), vi.fn()))
    act(() => result.current.startEditIncome(row))
    await act(async () => { await result.current.handleDeleteIncome(7) })
    expect(result.current.editingIncomeId).toBeNull()
  })
})

import { render, screen, fireEvent } from '@testing-library/react'
import IncomePage from '../pages/IncomePage.jsx'

describe('Income page', () => {
  const base = {
    income: [row],
    incomeSummary: null,
    incomeForm: { date: '', source: '', note: '', amount: '', currency: '' },
    setIncomeForm: () => {},
    savingIncome: false,
    onAddIncome: (e) => e.preventDefault(),
    onDeleteIncome: () => {},
    currencies: [],
    baseCurrency: 'SEK',
  }

  it('the pencil on a row starts editing it', () => {
    const onEditIncome = vi.fn()
    render(<IncomePage {...base} onEditIncome={onEditIncome} onCancelEditIncome={() => {}} />)
    fireEvent.click(screen.getByLabelText('Edit income Salary'))
    expect(onEditIncome).toHaveBeenCalledWith(row)
  })

  it('shows Save and Cancel while editing', () => {
    const onCancelEditIncome = vi.fn()
    render(<IncomePage {...base} editingIncomeId={7} onEditIncome={() => {}} onCancelEditIncome={onCancelEditIncome} />)
    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancelEditIncome).toHaveBeenCalled()
  })
})

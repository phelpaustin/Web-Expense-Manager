import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', () => ({
  importExpenses: vi.fn(),
  createExpense: vi.fn(),
  analyzeStatement: vi.fn(),
  previewStatement: vi.fn(),
  commitStatement: vi.fn(),
  assistStatement: vi.fn(),
  saveImportProfile: vi.fn(),
}))

import * as api from '../api/client.js'
import ImportPage from '../pages/ImportPage.jsx'

const OPTIONS = { currencies: ['SEK', 'EUR'], units: ['Count', 'kg'], categories: ['Food'], shops: ['ICA'] }

const SKIPPED = {
  added: 3, skipped: 1, errors: [],
  skipped_rows: [{ reason: 'Bad amount', date: '2026-09-03', category: 'Food', subcategory: '', description: 'Milk', amount: '', quantity: 1, unit: 'Count', shop: 'ICA', brand: '', currency: 'SEK' }],
}

function setup() {
  const onImported = vi.fn(async () => {})
  const onError = vi.fn()
  render(
    <MemoryRouter>
      <ImportPage options={OPTIONS} onImported={onImported} onError={onError} />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('tab', { name: 'Expense file' }))
  return { onImported, onError }
}

const pick = () => fireEvent.change(screen.getByLabelText('Expense file'), { target: { files: [new File(['x'], 'e.csv')] } })

beforeEach(() => vi.clearAllMocks())

describe('import page tabs', () => {
  it('has both kinds of import in one place, bank statement first', () => {
    setup()
    expect(screen.getByRole('tab', { name: 'Bank statement' }).getAttribute('aria-selected')).toBe('false')
    expect(screen.getByRole('tab', { name: 'Expense file' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByLabelText('Statement file')).toBeTruthy() // the statement tab stays mounted, just hidden
  })

  it('keeps a half-set-up statement when switching tabs', async () => {
    setup()
    api.analyzeStatement.mockResolvedValue({ header_row: 0, columns: ['Date', 'Amount'], rows: [], mapping: { header_row: 0, date: 'Date', amount: 'Amount', sign: 'negative_is_expense', date_order: 'auto', rules: [], include_expenses: true, include_income: true }, notes: [], problems: [], signature: 'abc12345', profile: null, ai_available: false })
    api.previewStatement.mockResolvedValue({ problems: [], summary: null, rows: [] })
    fireEvent.click(screen.getByRole('tab', { name: 'Bank statement' }))
    fireEvent.change(screen.getByLabelText('Statement file'), { target: { files: [new File(['x'], 's.csv')] } })
    await screen.findByLabelText('Date column')
    fireEvent.click(screen.getByRole('tab', { name: 'Expense file' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Bank statement' }))
    expect(screen.getByLabelText('Date column').value).toBe('Date')
  })
})

describe('expense file import', () => {
  it('imports with the chosen currency, reports the result and refreshes the app data', async () => {
    const { onImported } = setup()
    api.importExpenses.mockResolvedValue({ added: 5, skipped: 2, errors: ['x'], skipped_rows: [] })
    fireEvent.change(screen.getByLabelText('Currency for imported rows'), { target: { value: 'EUR' } })
    pick()
    fireEvent.click(screen.getByText('Import'))
    await screen.findByText('Imported 5 · skipped 2 · 1 row error(s)')
    expect(api.importExpenses.mock.calls[0][1]).toBe('EUR')
    expect(onImported).toHaveBeenCalledTimes(1)
  })

  it('offers the accounts currencies, not a fixed list', () => {
    setup()
    const options = [...screen.getByLabelText('Currency for imported rows').querySelectorAll('option')].map((o) => o.value)
    expect(options).toEqual(['', 'SEK', 'EUR'])
  })

  it('needs a file before it will import', () => {
    setup()
    expect(screen.getByText('Import').disabled).toBe(true)
  })

  it('shows a failed import as an error', async () => {
    setup()
    api.importExpenses.mockRejectedValue(new Error('Could not parse file'))
    pick()
    fireEvent.click(screen.getByText('Import'))
    await screen.findByText('Could not parse file')
  })

  it('lists skipped rows, and adds a fixed one back', async () => {
    const { onImported } = setup()
    api.importExpenses.mockResolvedValue(SKIPPED)
    api.createExpense.mockResolvedValue({})
    pick()
    fireEvent.click(screen.getByText('Import'))
    await screen.findByText('Skipped rows (1)'.replace('Skipped', 'Skipped'), { exact: false })
    expect(screen.getByText('Bad amount')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Row 1 amount'), { target: { value: '19.9' } })
    fireEvent.click(screen.getByTitle('Add this row'))
    await waitFor(() => expect(api.createExpense).toHaveBeenCalled())
    const sent = api.createExpense.mock.calls[0][0]
    expect(sent).toMatchObject({ description: 'Milk', amount: 19.9, quantity: 1, unit: 'Count', shop: 'ICA', currency: 'SEK' })
    await waitFor(() => expect(screen.queryByText('Bad amount')).toBeNull())
    expect(onImported).toHaveBeenCalledTimes(2) // after the import, and after the row was added
  })

  it('keeps a skipped row, with the reason, when adding it fails', async () => {
    setup()
    api.importExpenses.mockResolvedValue(SKIPPED)
    api.createExpense.mockRejectedValue(new Error('Amount is required'))
    pick()
    fireEvent.click(screen.getByText('Import'))
    await screen.findByText('Bad amount')
    fireEvent.click(screen.getByTitle('Add this row'))
    await screen.findByText('Amount is required')
  })

  it('lets a skipped row be dismissed', async () => {
    setup()
    api.importExpenses.mockResolvedValue(SKIPPED)
    pick()
    fireEvent.click(screen.getByText('Import'))
    await screen.findByText('Bad amount')
    fireEvent.click(screen.getByTitle('Dismiss'))
    expect(screen.queryByText('Bad amount')).toBeNull()
  })
})

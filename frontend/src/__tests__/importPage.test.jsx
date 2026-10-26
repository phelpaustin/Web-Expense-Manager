import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', () => ({
  analyzeStatement: vi.fn(),
  previewStatement: vi.fn(),
  commitStatement: vi.fn(),
  assistStatement: vi.fn(),
  saveImportProfile: vi.fn(),
}))

import * as api from '../api/client.js'
import ImportPage from '../pages/ImportPage.jsx'

const MAPPING = {
  header_row: 0, date: 'Date', description: 'Text', amount: 'Amount', sign: 'negative_is_expense',
  debit: null, credit: null, direction: null, category: null, shop: null, currency_column: null, currency: null,
  date_order: 'auto', skip_containing: [], rules: [], include_expenses: true, include_income: true,
}

const ANALYSIS = {
  filename: 's.csv', header_row: 0, columns: ['Date', 'Text', 'Amount', 'Debit', 'Credit'], grid_head: [], sample: [],
  total_rows: 2, mapping: MAPPING, notes: [], problems: [], signature: 'abc12345', profile: null, ai_available: true,
}

const row = (o) => ({
  line: 2, date: '2026-09-03', description: 'ICA', shop: '', amount: '245.50', currency: 'SEK', kind: 'expense',
  category: 'Groceries', subcategory: '', status: 'new', reason: '', overridden: false, rule: '', ...o,
})

const PREVIEW = {
  problems: [],
  summary: { rows: 3, new_expenses: 1, new_income: 1, duplicates: 1, skipped: 0, errors: 0, expense_total: { SEK: '245.50' }, income_total: { SEK: '32000.00' } },
  rows: [
    row({}),
    row({ line: 3, description: 'SALARY', amount: '32000.00', kind: 'income', category: '' }),
    row({ line: 4, description: 'OLD', status: 'duplicate', reason: 'Already in your records' }),
  ],
  truncated: false,
  categories: ['Groceries', 'Fun'],
}

function setup(props = {}) {
  const onError = vi.fn()
  const onImported = vi.fn(async () => {})
  render(
    <MemoryRouter>
      <ImportPage onError={onError} onImported={onImported} {...props} />
    </MemoryRouter>,
  )
  return { onError, onImported }
}

async function open(analysis = ANALYSIS) {
  api.analyzeStatement.mockResolvedValue(analysis)
  const file = new File(['x'], 's.csv', { type: 'text/csv' })
  fireEvent.change(screen.getByLabelText('Statement file'), { target: { files: [file] } })
  await screen.findByLabelText('Date column')
  await screen.findByText('SALARY')
  return file
}

const lastPreviewMapping = () => JSON.parse(JSON.stringify(api.previewStatement.mock.calls.at(-1)[1]))

beforeEach(() => {
  vi.clearAllMocks()
  api.previewStatement.mockResolvedValue(PREVIEW)
})

describe('statement import page', () => {
  it('reads the file, fills in the guessed columns and shows the preview', async () => {
    setup()
    await open()
    expect(api.analyzeStatement).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('Amount column').value).toBe('Amount')
    expect(screen.getByLabelText('Sign convention').value).toBe('negative_is_expense')
    expect(screen.getByText('Import 1 expense and 1 income')).toBeTruthy()
    expect(screen.getByText('Already in your records')).toBeTruthy()
    expect(lastPreviewMapping().amount).toBe('Amount')
  })

  it('lets the person say that positive amounts are expenses', async () => {
    setup()
    await open()
    fireEvent.change(screen.getByLabelText('Sign convention'), { target: { value: 'positive_is_expense' } })
    await waitFor(() => expect(lastPreviewMapping().sign).toBe('positive_is_expense'))
  })

  it('switches to separate debit and credit columns and clears the single amount column', async () => {
    setup()
    await open()
    fireEvent.click(screen.getByLabelText('Separate money-out and money-in columns'))
    fireEvent.change(screen.getByLabelText('Money out (debit) column'), { target: { value: 'Debit' } })
    fireEvent.change(screen.getByLabelText('Money in (credit) column'), { target: { value: 'Credit' } })
    await waitFor(() => {
      const m = lastPreviewMapping()
      expect([m.amount, m.debit, m.credit]).toEqual([null, 'Debit', 'Credit'])
    })
    expect(screen.queryByLabelText('Sign convention')).toBeNull()
  })

  it('sends only complete rules', async () => {
    setup()
    await open()
    fireEvent.click(screen.getByText('+ Add rule'))
    await new Promise((r) => setTimeout(r, 400))
    expect(lastPreviewMapping().rules).toEqual([]) // still being typed
    fireEvent.change(screen.getByLabelText('Rule 1 text'), { target: { value: 'swish' } })
    fireEvent.change(screen.getByLabelText('Rule 1 action'), { target: { value: 'income' } })
    await waitFor(() => expect(lastPreviewMapping().rules).toEqual([{ contains: 'swish', action: 'income', category: null }]))
  })

  it('sends a per-row choice and a category edit with the next preview', async () => {
    setup()
    await open()
    fireEvent.change(screen.getByLabelText('Line 3 is'), { target: { value: 'skip' } })
    fireEvent.change(screen.getByLabelText('Line 2 category'), { target: { value: 'Fun' } })
    await waitFor(() => {
      const [, , overrides, categories] = api.previewStatement.mock.calls.at(-1)
      expect(overrides).toEqual({ 3: 'skip' })
      expect(categories).toEqual({ 2: 'Fun' })
    })
  })

  it('does not let a duplicate row be changed', async () => {
    setup()
    await open()
    expect(screen.getByLabelText('Line 4 is').disabled).toBe(true)
  })

  it('filters rows by status', async () => {
    setup()
    await open()
    fireEvent.click(screen.getByRole('tab', { name: 'Already there' }))
    expect(screen.queryByText('SALARY')).toBeNull()
    expect(screen.getByText('OLD')).toBeTruthy()
  })

  it('asks the assistant, shows what it did, and previews the result', async () => {
    setup()
    await open()
    api.assistStatement.mockResolvedValue({
      mapping: { ...MAPPING, sign: 'positive_is_expense', rules: [{ contains: 'transfer', action: 'skip', category: null }] },
      explanation: 'Positive amounts are expenses; transfers are skipped.',
      notes: [],
      problems: [],
    })
    fireEvent.change(screen.getByLabelText('Instruction for the assistant'), { target: { value: 'skip transfers' } })
    fireEvent.click(screen.getByText('Apply'))
    await screen.findByText('Positive amounts are expenses; transfers are skipped.')
    expect(api.assistStatement.mock.calls[0][2]).toBe('skip transfers')
    expect(screen.getByLabelText('Sign convention').value).toBe('positive_is_expense')
    expect(screen.getByLabelText('Rule 1 text').value).toBe('transfer')
    await waitFor(() => expect(lastPreviewMapping().rules[0].contains).toBe('transfer'))
  })

  it('hides the assistant when the server has no AI configured', async () => {
    setup()
    await open({ ...ANALYSIS, ai_available: false })
    expect(screen.queryByLabelText('Instruction for the assistant')).toBeNull()
  })

  it('reports an assistant failure without losing the mapping', async () => {
    const { onError } = setup()
    await open()
    api.assistStatement.mockRejectedValue(new Error('The assistant is unavailable right now.'))
    fireEvent.change(screen.getByLabelText('Instruction for the assistant'), { target: { value: 'hi' } })
    fireEvent.click(screen.getByText('Apply'))
    await waitFor(() => expect(onError).toHaveBeenCalledWith('The assistant is unavailable right now.'))
    expect(screen.getByLabelText('Amount column').value).toBe('Amount')
  })

  it('shows mapping problems instead of a preview', async () => {
    setup()
    api.previewStatement.mockResolvedValue({ problems: ['Choose the amount column'], summary: null, rows: [] })
    api.analyzeStatement.mockResolvedValue({ ...ANALYSIS, problems: ['Choose the amount column'] })
    fireEvent.change(screen.getByLabelText('Statement file'), { target: { files: [new File(['x'], 's.csv')] } })
    await screen.findByRole('alert')
    expect(screen.getByText('Choose the amount column')).toBeTruthy()
    await waitFor(() => expect(screen.getByText(/Fix the columns above/)).toBeTruthy())
  })

  it('imports, refreshes the app data and shows what happened', async () => {
    const { onImported } = setup()
    const file = await open()
    api.commitStatement.mockResolvedValue({ added_expenses: 1, added_income: 1, duplicates: 1, skipped: 0, errors: 0 })
    fireEvent.click(screen.getByText('Import 1 expense and 1 income'))
    await screen.findByText(/Imported 1 expense and 1 income\. 1 already in your records\./)
    expect(api.commitStatement.mock.calls[0][0]).toBe(file)
    expect(onImported).toHaveBeenCalledTimes(1)
    expect(screen.queryByLabelText('Date column')).toBeNull() // back to the start
  })

  it('saves as expenses unless told otherwise', async () => {
    setup()
    await open()
    expect(screen.getByRole('radio', { name: /Expenses/ }).checked).toBe(true)
    expect(api.previewStatement.mock.calls.at(-1)[4]).toBe('expenses')
    expect(screen.getByText('New expenses')).toBeTruthy()
  })

  it('offers to save the expenses as bills, and previews and commits that way', async () => {
    const { onImported } = setup()
    await open()
    fireEvent.click(screen.getByRole('radio', { name: /Bills/ }))
    await waitFor(() => expect(api.previewStatement.mock.calls.at(-1)[4]).toBe('bills'))
    expect(screen.getByText('New bills')).toBeTruthy()
    expect(screen.getByText(/count as spending straight away/)).toBeTruthy()
    api.commitStatement.mockResolvedValue({ save_as: 'bills', added_expenses: 0, added_bills: 1, recorded_bills: 1, added_income: 1, duplicates: 1, skipped: 0, errors: 0 })
    fireEvent.click(screen.getByText('Import 1 bill and 1 income'))
    await screen.findByText(/Imported 1 bill and 1 income\. 1 counted as spending; itemise them whenever you like\. 1 already in your records\./)
    expect(api.commitStatement.mock.calls[0][4]).toBe('bills')
    expect(screen.getByRole('link', { name: 'See bills' }).getAttribute('href')).toBe('/bills')
    expect(onImported).toHaveBeenCalledTimes(1)
  })

  it('says bills will wait when the setting is off', async () => {
    setup({ options: { count_bills_as_spending: false } })
    await open()
    fireEvent.click(screen.getByRole('radio', { name: /Bills/ }))
    expect(screen.getByText(/do not count as spending until you record them/)).toBeTruthy()
  })

  it('does not offer to import when nothing is new', async () => {
    setup()
    api.previewStatement.mockResolvedValue({ ...PREVIEW, summary: { ...PREVIEW.summary, new_expenses: 0, new_income: 0 } })
    await open()
    expect(screen.getByText('Nothing new to import').closest('button').disabled).toBe(true)
  })

  it('saves the mapping under a name with the files signature', async () => {
    setup()
    await open()
    api.saveImportProfile.mockResolvedValue({ id: 1, name: 'My bank' })
    fireEvent.change(screen.getByLabelText('Name for this mapping'), { target: { value: 'My bank' } })
    fireEvent.click(screen.getByText('Save mapping'))
    await screen.findByText(/Saved as “My bank”/)
    expect(api.saveImportProfile.mock.calls[0].slice(0, 2)).toEqual(['My bank', 'abc12345'])
  })

  it('says when a saved mapping was used', async () => {
    setup()
    await open({ ...ANALYSIS, profile: { id: 5, name: 'My bank' }, notes: ['Used your saved mapping “My bank”.'] })
    expect(screen.getByText('Using your saved mapping “My bank”.')).toBeTruthy()
    expect(screen.getByLabelText('Name for this mapping').value).toBe('My bank')
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'
import BillsPage from '../pages/BillsPage.jsx'

const BILLS = [
  { id: 1, date: '2026-07-21', shop: 'INDO PAK MALMO', amount: 82.5, currency: 'SEK', note: 'Bulk import', status: 'pending', has_receipt: false, possible_duplicate: false, item_count: 0 },
  { id: 2, date: '2026-07-21', shop: 'LIDL', amount: 35.91, currency: 'SEK', note: '', status: 'total_only', has_receipt: true, possible_duplicate: false, item_count: 1 },
  { id: 3, date: '2026-07-20', shop: 'ICA KVANTUM', amount: 189.29, currency: 'SEK', note: '', status: 'itemised', has_receipt: false, possible_duplicate: false, item_count: 3 },
  { id: 4, date: '2026-07-19', shop: 'WILLYS', amount: 45.3, currency: 'SEK', note: 'Bulk import', status: 'pending', has_receipt: false, possible_duplicate: true, item_count: 0 },
  { id: 5, date: '2026-07-18', shop: 'Unreadable receipt', amount: 0, currency: 'SEK', note: 'my note', status: 'pending', has_receipt: true, possible_duplicate: false, item_count: 0 },
]

const ACTIONS = ['add', 'uploadBill', 'bulkUpload', 'recordTotal', 'bulkRecord', 'undo', 'itemise', 'dismissDuplicate', 'remove', 'bulkDelete', 'uploadReceipt', 'viewReceipt', 'deleteReceipt', 'toggleCount']

function makeState(overrides = {}) {
  return {
    data: { items: BILLS, total: 58, page: 1, page_size: 25, counts: { pending: 40, total_only: 12, itemised: 6, all: 58 } },
    query: { status: 'pending', q: '', date_from: '', date_to: '', sort: 'date_desc', page: 1, page_size: 25 },
    setQuery: vi.fn(),
    loading: false,
    selected: new Set(),
    toggleSelect: vi.fn(),
    selectPage: vi.fn(),
    clearSelection: vi.fn(),
    notice: null,
    setNotice: vi.fn(),
    form: { date: '', shop: '', amount: '', note: '', currency: '' },
    setForm: vi.fn(),
    actions: Object.fromEntries(ACTIONS.map((k) => [k, vi.fn()])),
    ...overrides,
  }
}

const OPTIONS = { categories: ['Food', 'Transport'], currencies: ['EUR', 'SEK'], base_currency: 'SEK', count_bills_as_spending: true }

const renderPage = (state = makeState(), options = OPTIONS) => {
  render(<BillsPage state={state} options={options} />)
  return state
}
const row = (text) => screen.getByText(text).closest('tr')

describe('Bills page: tabs and counts', () => {
  it('shows every tab with its count and marks the active one', () => {
    renderPage()
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((t) => t.textContent.replace(/\s+/g, ' ').trim())).toEqual(['To itemise 40', 'Total only 12', 'Itemised 6', 'All 58'])
    expect(screen.getByRole('tab', { name: /To itemise/ }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tab', { name: /Itemised/ }).getAttribute('aria-selected')).toBe('false')
  })

  it('switches tab through setQuery', () => {
    const state = renderPage()
    fireEvent.click(screen.getByRole('tab', { name: /Total only/ }))
    expect(state.setQuery).toHaveBeenCalledWith({ status: 'total_only' })
  })
})

describe('Bills page: actions depend on the bill status', () => {
  it('to itemise: Itemise, Record total and Delete (no Undo)', () => {
    const state = renderPage()
    const r = within(row('INDO PAK MALMO'))
    expect(r.getByText('To itemise')).toBeTruthy()
    fireEvent.click(r.getByRole('button', { name: 'Itemise' }))
    expect(state.actions.itemise).toHaveBeenCalledWith(expect.objectContaining({ id: 1, shop: 'INDO PAK MALMO' }))
    fireEvent.click(r.getByRole('button', { name: 'Record total' }))
    expect(state.actions.recordTotal).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), 'Bills')
    fireEvent.click(r.getByRole('button', { name: 'Delete' }))
    expect(state.actions.remove).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    expect(r.queryByRole('button', { name: 'Undo' })).toBeNull()
  })

  it('total only: can still be itemised or undone, but not deleted or recorded again', () => {
    const state = renderPage()
    const r = within(row('LIDL'))
    expect(r.getByText('Total only')).toBeTruthy()
    fireEvent.click(r.getByRole('button', { name: 'Itemise' }))
    expect(state.actions.itemise).toHaveBeenCalledWith(expect.objectContaining({ id: 2, status: 'total_only' }))
    fireEvent.click(r.getByRole('button', { name: 'Undo' }))
    expect(state.actions.undo).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
    expect(r.queryByRole('button', { name: 'Delete' })).toBeNull()
    expect(r.queryByRole('button', { name: 'Record total' })).toBeNull()
  })

  it('itemised: shows the item count and can only be deleted', () => {
    const state = renderPage()
    const r = within(row('ICA KVANTUM'))
    expect(r.getByText('Itemised · 3 items')).toBeTruthy()
    expect(r.queryByRole('button', { name: 'Itemise' })).toBeNull()
    expect(r.queryByRole('button', { name: 'Record total' })).toBeNull()
    expect(r.queryByRole('button', { name: 'Undo' })).toBeNull()
    fireEvent.click(r.getByRole('button', { name: 'Delete' }))
    expect(state.actions.remove).toHaveBeenCalledWith(expect.objectContaining({ id: 3 }))
  })

  it('flags a possible duplicate and lets you clear the warning', () => {
    const state = renderPage()
    const tr = row('WILLYS')
    expect(tr.className).toContain('row-flagged')
    expect(within(tr).getByText(/possible duplicate/)).toBeTruthy()
    fireEvent.click(within(tr).getByRole('button', { name: 'Not a duplicate' }))
    expect(state.actions.dismissDuplicate).toHaveBeenCalledWith(4)
    expect(within(row('INDO PAK MALMO')).queryByText(/possible duplicate/)).toBeNull()
  })

  it('shows "no amount" for a bill whose total could not be read', () => {
    renderPage()
    expect(within(row('Unreadable receipt')).getByText('no amount')).toBeTruthy()
    expect(screen.getByText(/my note/)).toBeTruthy() // user notes show; the "Bulk import" label does not
    expect(screen.queryByText(/Bulk import/)).toBeNull()
  })

  it('records with the category chosen in the bulk bar', () => {
    const state = makeState({ selected: new Set([1, 4]) })
    renderPage(state)
    fireEvent.change(screen.getByLabelText('Category for recorded totals'), { target: { value: 'Food' } })
    fireEvent.click(within(row('INDO PAK MALMO')).getByRole('button', { name: 'Record total' }))
    expect(state.actions.recordTotal).toHaveBeenCalledWith(expect.anything(), 'Food')
  })
})

describe('Bills page: receipts', () => {
  it('attach when there is none; view and remove when there is', () => {
    const state = renderPage()
    expect(within(row('INDO PAK MALMO')).getByText(/Attach/)).toBeTruthy()
    const withReceipt = within(row('LIDL'))
    fireEvent.click(withReceipt.getByRole('button', { name: /View/ }))
    expect(state.actions.viewReceipt).toHaveBeenCalledWith(2)
    fireEvent.click(withReceipt.getByTitle('Remove the receipt'))
    expect(state.actions.deleteReceipt).toHaveBeenCalledWith(2)
    expect(withReceipt.queryByText(/Attach/)).toBeNull()
  })

  it('uploads the chosen file to that bill', () => {
    const state = renderPage()
    const input = within(row('INDO PAK MALMO')).getByText(/Attach/).querySelector('input')
    const file = new File(['x'], 'r.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [file] } })
    expect(state.actions.uploadReceipt).toHaveBeenCalledWith(1, file)
  })
})

describe('Bills page: selection and the bulk bar', () => {
  it('ticking a row toggles it', () => {
    const state = renderPage()
    fireEvent.click(screen.getByLabelText('Select INDO PAK MALMO'))
    expect(state.toggleSelect).toHaveBeenCalledWith(1)
  })

  it('has no bulk bar until something is selected', () => {
    renderPage()
    expect(screen.queryByRole('region', { name: 'Selected bills' })).toBeNull()
  })

  it('records or deletes the selection', () => {
    const state = makeState({ selected: new Set([1, 2, 4]) })
    renderPage(state)
    const bar = within(screen.getByRole('region', { name: 'Selected bills' }))
    expect(bar.getByText('3 selected')).toBeTruthy()
    fireEvent.click(bar.getByRole('button', { name: 'Record total' }))
    expect(state.actions.bulkRecord).toHaveBeenCalledWith('Bills')
    fireEvent.click(bar.getByRole('button', { name: 'Delete' }))
    expect(state.actions.bulkDelete).toHaveBeenCalled()
    fireEvent.click(bar.getByRole('button', { name: 'Clear' }))
    expect(state.clearSelection).toHaveBeenCalled()
  })

  it('offers Bills plus the user categories without duplicating Bills', () => {
    renderPage(makeState({ selected: new Set([1]) }), { ...OPTIONS, categories: ['Food', 'Bills'] })
    const names = [...screen.getByLabelText('Category for recorded totals').querySelectorAll('option')].map((o) => o.value)
    expect(names).toEqual(['Bills', 'Food'])
  })

  it('selects every row on the page, or unselects them when all are selected', () => {
    const state = renderPage()
    fireEvent.click(screen.getByLabelText('Select all bills on this page'))
    expect(state.selectPage).toHaveBeenCalled()
  })

  it('unselects the page when every row is already ticked', () => {
    const state = makeState({ selected: new Set(BILLS.map((b) => b.id)) })
    renderPage(state)
    fireEvent.click(screen.getByLabelText('Select all bills on this page'))
    expect(state.toggleSelect).toHaveBeenCalledTimes(BILLS.length)
  })
})

describe('Bills page: the spending setting', () => {
  it('reflects the setting and toggles it', () => {
    const state = renderPage()
    const box = screen.getByLabelText(/Count new bills as spending right away/)
    expect(box.checked).toBe(true)
    expect(screen.getByText(/count towards budgets/i)).toBeTruthy()
    fireEvent.click(box)
    expect(state.actions.toggleCount).toHaveBeenCalledWith(false)
  })

  it('explains what happens when it is off', () => {
    renderPage(makeState(), { ...OPTIONS, count_bills_as_spending: false })
    expect(screen.getByLabelText(/Count new bills as spending right away/).checked).toBe(false)
    expect(screen.getByText(/not counted until you record or itemise/i)).toBeTruthy()
  })
})

describe('Bills page: search, sort and filters', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('debounces the search box', () => {
    const state = renderPage()
    fireEvent.change(screen.getByLabelText('Search bills'), { target: { value: 'lidl' } })
    expect(state.setQuery).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(450))
    expect(state.setQuery).toHaveBeenCalledWith({ q: 'lidl' })
  })

  it('sorts and filters by date', () => {
    const state = renderPage()
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'amount_desc' } })
    expect(state.setQuery).toHaveBeenLastCalledWith({ sort: 'amount_desc' })
    fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-07-01' } })
    expect(state.setQuery).toHaveBeenLastCalledWith({ date_from: '2026-07-01' })
    fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-07-31' } })
    expect(state.setQuery).toHaveBeenLastCalledWith({ date_to: '2026-07-31' })
  })

  it('offers to clear active filters', () => {
    const state = makeState({ query: { status: 'pending', q: 'lidl', date_from: '', date_to: '', sort: 'date_desc', page: 1, page_size: 25 } })
    renderPage(state)
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(state.setQuery).toHaveBeenCalledWith({ q: '', date_from: '', date_to: '' })
  })
})

describe('Bills page: pagination and empty states', () => {
  it('pages through the list 25 at a time', () => {
    const state = renderPage()
    expect(screen.getByText('Showing 1–25 of 58')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(state.setQuery).toHaveBeenCalledWith({ page: 2 })
    fireEvent.change(screen.getByLabelText('Rows per page'), { target: { value: '50' } })
    expect(state.setQuery).toHaveBeenCalledWith({ page_size: 50 })
  })

  it.each([
    ['pending', /Nothing is waiting/],
    ['total_only', /recorded as a total only/],
    ['itemised', /No itemised bills yet/],
    ['all', /Upload a receipt, import a bank statement/],
  ])('says something useful when the %s tab is empty', (status, text) => {
    const state = makeState({
      data: { items: [], total: 0, page: 1, page_size: 25, counts: { pending: 0, total_only: 0, itemised: 0, all: 0 } },
      query: { status, q: '', date_from: '', date_to: '', sort: 'date_desc', page: 1, page_size: 25 },
    })
    renderPage(state)
    expect(screen.getByText(text)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('says nothing matched when a search finds nothing', () => {
    const state = makeState({
      data: { items: [], total: 0, page: 1, page_size: 25, counts: { pending: 0, total_only: 0, itemised: 0, all: 0 } },
      query: { status: 'pending', q: 'zzz', date_from: '', date_to: '', sort: 'date_desc', page: 1, page_size: 25 },
    })
    renderPage(state)
    expect(screen.getByText('No bills match your search.')).toBeTruthy()
  })
})

describe('Bills page: adding, uploading and notices', () => {
  it('uploads a receipt and imports a statement', () => {
    const state = renderPage()
    const receipt = new File(['x'], 'r.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByText(/Upload receipt/).querySelector('input'), { target: { files: [receipt] } })
    expect(state.actions.uploadBill).toHaveBeenCalledWith(receipt)
    const sheet = new File(['x'], 's.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByText(/Import bank statement/).querySelector('input'), { target: { files: [sheet] } })
    expect(state.actions.bulkUpload).toHaveBeenCalledWith(sheet)
  })

  it('opens the add form and submits it', () => {
    const state = renderPage()
    expect(screen.queryByPlaceholderText('Shop')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Add bill/ }))
    fireEvent.change(screen.getByPlaceholderText('Shop'), { target: { value: 'Coop' } })
    expect(state.setForm).toHaveBeenCalledWith(expect.objectContaining({ shop: 'Coop' }))
    fireEvent.submit(screen.getByPlaceholderText('Shop').closest('form'))
    expect(state.actions.add).toHaveBeenCalled()
  })

  it('shows and dismisses a notice with its details', () => {
    const state = renderPage(makeState({ notice: { text: 'Imported 3 bills.', details: ['Row 2: bad amount'] } }))
    expect(screen.getByText('Imported 3 bills.')).toBeTruthy()
    expect(screen.getByText('Row 2: bad amount')).toBeTruthy()
    fireEvent.click(screen.getByTitle('Dismiss'))
    expect(state.setNotice).toHaveBeenCalledWith(null)
  })

  it('summarises a long list of skipped rows', () => {
    const details = Array.from({ length: 25 }, (_, i) => `Row ${i + 2}: bad`)
    renderPage(makeState({ notice: { text: 'x', details } }))
    expect(screen.getByText('…and 5 more')).toBeTruthy()
  })

  it('shows a loading message only when there is nothing to show yet', () => {
    const empty = { items: [], total: 0, page: 1, page_size: 25, counts: { pending: 0, total_only: 0, itemised: 0, all: 0 } }
    renderPage(makeState({ loading: true, data: empty }))
    expect(screen.getByText('Loading…')).toBeTruthy()
  })
})

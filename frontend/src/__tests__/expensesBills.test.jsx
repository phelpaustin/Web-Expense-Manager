import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import * as client from '../api/client.js'
import ExpensesPage from '../pages/ExpensesPage.jsx'
import { useExpenseHandlers } from '../hooks/useExpenseHandlers.js'

const OPTIONS = {
  categories: ['Food', 'Bills'], subcategories: {}, units: ['Count'], shops: [],
  currencies: ['EUR', 'SEK'], base_currency: 'SEK',
}

const NORMAL = {
  id: 1, date: '2026-07-20', category: 'Food', subcategory: '', shop: '', description: 'Milk', quantity: 1, unit: 'Count',
  amount: 20, currency: 'SEK', price_per_unit: 20, group_id: null, source_bill_id: null, bill_total_only: false, created_by: null,
}
const TOTAL_ONLY = {
  id: 2, date: '2026-07-21', category: 'Bills', subcategory: '', shop: '', description: 'LIDL145MALMOBA', quantity: 1, unit: 'Count',
  amount: 35.91, currency: 'SEK', price_per_unit: 35.91, group_id: null, source_bill_id: 77, bill_total_only: true, created_by: null,
}

let loadAll, setError, where
let spaces = { trips: [], groups: [] }
function Where() {
  where = useLocation()
  return null
}

// The real expense hook drives the page, so the form really behaves as it does in the app.
function Harness() {
  const e = useExpenseHandlers(loadAll, setError)
  return (
    <>
      <Where />
      <ExpensesPage
        form={e.form} setForm={e.setForm} saving={e.saving} onAdd={e.handleAdd} onAddBill={e.handleAddBill}
        editingId={e.editingId} editForm={e.editForm} setEditForm={e.setEditForm} startEdit={e.startEdit}
        cancelEdit={e.cancelEdit} saveEdit={e.saveEdit} onDelete={e.handleDelete} options={OPTIONS}
        onExport={e.handleExport} onBulkUpdate={e.handleBulkUpdate} onBulkCopy={e.handleBulkCopy}
        trips={spaces.trips} groups={spaces.groups} onError={setError}
      />
    </>
  )
}

const renderAt = (state) =>
  render(
    <MemoryRouter initialEntries={[{ pathname: '/expenses', state }]}>
      <Harness />
    </MemoryRouter>,
  )

const BILL = { id: 77, date: '2026-07-21', shop: 'LIDL145MALMOBA', amount: 35.91, currency: 'SEK', status: 'total_only', has_receipt: true }

beforeEach(() => {
  vi.clearAllMocks()
  loadAll = vi.fn(async () => {})
  setError = vi.fn()
  spaces = { trips: [], groups: [] }
  client.fetchExpenses.mockImplementation(async () => ({ items: [NORMAL, TOTAL_ONLY], total: 2 }))
})

const rowOf = (text) => screen.getByText(text).closest('tr')
// The default view groups expenses under collapsed bill headers.
const header = async (name) => (await screen.findByText(new RegExp(`· ${name} ·`))).closest('tr')
const addItem = async (amount) => {
  fireEvent.change(screen.getByPlaceholderText('Category'), { target: { value: 'Food' } })
  fireEvent.change(screen.getByPlaceholderText('Amount'), { target: { value: String(amount) } })
  fireEvent.click(screen.getByRole('button', { name: /Add item/ }))
  await screen.findByLabelText(/Receipt total/)
}
const flatView = async () => {
  await screen.findByRole('button', { name: /Flat view/ })
  fireEvent.click(screen.getByRole('button', { name: /Flat view/ }))
}

describe('total-only expenses stand out on the Expenses page', () => {
  it('flags the bill header (without expanding) and offers Itemise; ordinary bills get neither', async () => {
    renderAt(undefined)
    const special = await header('LIDL145MALMOBA') // named from its description since it has no shop
    expect(special.className).toContain('row-total-only')
    expect(within(special).getByText(/Total only/)).toBeTruthy()
    expect(within(special).getByRole('button', { name: 'Itemise' })).toBeTruthy()
    const ordinary = await header('Milk')
    expect(ordinary.className).not.toContain('row-total-only')
    expect(within(ordinary).queryByText(/Total only/)).toBeNull()
    expect(within(ordinary).queryByRole('button', { name: 'Itemise' })).toBeNull()
  })

  it('clicking Itemise on the header does not also expand the group', async () => {
    renderAt(undefined)
    const special = await header('LIDL145MALMOBA')
    fireEvent.click(within(special).getByRole('button', { name: 'Itemise' }))
    await screen.findByRole('status')
    expect(special.textContent).toContain('▸') // still collapsed
  })

  it('in the flat view the row itself is highlighted, badged and itemisable', async () => {
    renderAt(undefined)
    await flatView()
    const special = (await screen.findByText('LIDL145MALMOBA')).closest('tr')
    expect(special.className).toContain('row-total-only')
    expect(within(special).getByText(/Total only/)).toBeTruthy()
    expect(within(special).getByRole('button', { name: 'Itemise' })).toBeTruthy()
    const ordinary = rowOf('Milk')
    expect(ordinary.className).not.toContain('row-total-only')
    expect(within(ordinary).queryByText(/Total only/)).toBeNull()
    expect(within(ordinary).queryByRole('button', { name: 'Itemise' })).toBeNull()
  })

  it('expanding a group shows the highlighted row inside it', async () => {
    renderAt(undefined)
    fireEvent.click(await header('LIDL145MALMOBA'))
    const inner = (await screen.findByText('LIDL145MALMOBA', { selector: 'td' })).closest('tr')
    expect(inner.className).toContain('row-total-only')
  })

  it('can filter to total-only bills', async () => {
    renderAt(undefined)
    await header('Milk')
    fireEvent.click(screen.getByLabelText('Total-only bills'))
    await waitFor(() => expect(client.fetchExpenses.mock.calls.at(-1)[0]).toMatchObject({ total_only: 'true', page: 1 }))
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(client.fetchExpenses.mock.calls.at(-1)[0].total_only).toBe(''))
  })

  it('a group that mixes a total-only line with items is badged but not made a one-click itemise', async () => {
    client.fetchExpenses.mockImplementation(async () => ({
      items: [{ ...TOTAL_ONLY, shop: 'LIDL' }, { ...NORMAL, id: 9, shop: 'LIDL', date: '2026-07-21', description: 'Bread' }],
      total: 2,
    }))
    renderAt(undefined)
    const mixed = await header('LIDL')
    expect(within(mixed).getByText(/Total only/)).toBeTruthy()
    expect(mixed.className).not.toContain('row-total-only')
    expect(within(mixed).queryByRole('button', { name: 'Itemise' })).toBeNull()
  })
})

describe('itemising from a total-only row', () => {
  it('opens bill mode for that bill and says the single line will be replaced', async () => {
    renderAt(undefined)
    fireEvent.click(within(await header('LIDL145MALMOBA')).getByRole('button', { name: 'Itemise' }))
    const banner = await screen.findByRole('status')
    expect(within(banner).getByText(/Itemising: LIDL145MALMOBA/)).toBeTruthy()
    expect(within(banner).getByText(/replaced by these items/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Cancel itemising/ })).toBeTruthy()
    await addItem(10)
    expect(screen.getByLabelText(/Receipt total/).value).toBe('35.91') // the bill total is prefilled
    expect(screen.getByText(/less than the receipt total/)).toBeTruthy() // so a short item list is flagged
  })

  it('submits the items against the bill, then leaves bill mode', async () => {
    renderAt(undefined)
    fireEvent.click(within(await header('LIDL145MALMOBA')).getByRole('button', { name: 'Itemise' }))
    await screen.findByRole('status')

    fireEvent.change(screen.getByPlaceholderText('Category'), { target: { value: 'Food' } })
    fireEvent.change(screen.getByPlaceholderText('Amount'), { target: { value: '35.91' } })
    fireEvent.click(screen.getByRole('button', { name: /Add item/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Submit bill/ }))

    await waitFor(() => expect(client.createExpensesBulk).toHaveBeenCalled())
    const [items, billId] = client.createExpensesBulk.mock.calls[0]
    expect(billId).toBe(77)
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ date: '2026-07-21', shop: 'LIDL145MALMOBA', category: 'Food', amount: 35.91, currency: 'SEK' })
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    expect(loadAll).toHaveBeenCalled()
  })

  it('cancelling clears the bill without sending anything', async () => {
    renderAt(undefined)
    fireEvent.click(within(await header('LIDL145MALMOBA')).getByRole('button', { name: 'Itemise' }))
    await screen.findByRole('status')
    fireEvent.click(within(screen.getByRole('status')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    expect(client.createExpensesBulk).not.toHaveBeenCalled()
  })
})

describe('Add by bill (a new bill, not itemising an existing one)', () => {
  it('asks the server to make its bill record, so it shows on the Bills page', async () => {
    renderAt(undefined)
    await header('Milk')
    fireEvent.click(screen.getByRole('button', { name: /Add by bill/ }))
    fireEvent.change(document.querySelector('#add-expense-panel input[type=date]'), { target: { value: '2026-07-21' } })
    await addItem(12)
    fireEvent.click(await screen.findByRole('button', { name: /Submit bill/ }))
    await waitFor(() => expect(client.createExpensesBulk).toHaveBeenCalled())
    const [items, billId, options] = client.createExpensesBulk.mock.calls[0]
    expect(items).toHaveLength(1)
    expect(billId).toBeUndefined()
    expect(options).toEqual({ asBill: true })
  })

  it('itemising an existing bill links to it instead (no second bill is made)', async () => {
    renderAt({ itemiseBill: { ...BILL, status: 'pending' } })
    await screen.findByRole('status')
    await addItem(35.91)
    fireEvent.click(await screen.findByRole('button', { name: /Submit bill/ }))
    await waitFor(() => expect(client.createExpensesBulk).toHaveBeenCalled())
    const [, billId, options] = client.createExpensesBulk.mock.calls[0]
    expect(billId).toBe(77)
    expect(options).toBeUndefined()
  })
})

describe('arriving from the Bills page', () => {
  it('picks up the bill from the navigation state, prefills bill mode and clears the state', async () => {
    renderAt({ itemiseBill: { ...BILL, status: 'pending' } })
    const banner = await screen.findByRole('status')
    expect(within(banner).getByText(/Itemising: LIDL145MALMOBA/)).toBeTruthy()
    expect(within(banner).getByText(/becomes itemised when you submit/)).toBeTruthy() // no total line to replace
    await addItem(35.91)
    expect(screen.getByLabelText(/Receipt total/).value).toBe('35.91')
    expect(screen.getByText(/Matches the receipt total/)).toBeTruthy()
    await waitFor(() => expect(where.state).toBeNull()) // a refresh must not start itemising again
  })

  it('offers the receipt when the bill has one, and not when it is known to have none', async () => {
    const { unmount } = renderAt({ itemiseBill: BILL })
    const banner = await screen.findByRole('status')
    fireEvent.click(within(banner).getByRole('button', { name: /View receipt/ }))
    expect(client.viewReceipt).toHaveBeenCalledWith(77)
    unmount()
    renderAt({ itemiseBill: { ...BILL, has_receipt: false } })
    const again = await screen.findByRole('status')
    expect(within(again).queryByRole('button', { name: /View receipt/ })).toBeNull()
  })

  it('shows nothing special for an ordinary visit', async () => {
    renderAt(undefined)
    await header('Milk')
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByRole('button', { name: /Add by bill/ })).toBeTruthy()
  })
})

// ── re-itemising ──
const ITEMISED_BILL = { id: 88, date: '2026-07-20', shop: 'ICA Nära', amount: 100, currency: 'SEK', status: 'itemised', has_receipt: false }
const ITEM = (id, extra = {}) => ({
  id, date: '2026-07-20', category: 'Food', subcategory: '', shop: 'ICA Nära', description: `Item ${id}`, quantity: 1, unit: 'Count',
  amount: 40, currency: 'SEK', price_per_unit: 40, group_id: null, source_bill_id: 88, bill_total_only: false, brand: '', ...extra,
})

describe('re-itemising an itemised bill', () => {
  beforeEach(() => {
    client.fetchBillItems.mockImplementation(async () => [ITEM(1), ITEM(2, { amount: 60, category: 'Household', description: 'Soap' })])
    client.fetchBill.mockImplementation(async () => ITEMISED_BILL)
  })

  it('loads the current items into bill mode, with its details, and says saving replaces them', async () => {
    renderAt({ itemiseBill: ITEMISED_BILL })
    const banner = await screen.findByRole('status')
    expect(client.fetchBillItems).toHaveBeenCalledWith(88)
    expect(within(banner).getByText(/Editing items: ICA Nära/)).toBeTruthy()
    expect(within(banner).getByText(/Saving replaces this bill's current items/)).toBeTruthy()
    expect(await screen.findByText('Soap')).toBeTruthy()
    expect(screen.getByText('Item 1')).toBeTruthy()
    expect(screen.getByLabelText(/Receipt total/).value).toBe('100')
    expect(screen.getByText(/Matches the receipt total/)).toBeTruthy() // 40 + 60 = 100
    expect(screen.getByRole('button', { name: /Cancel itemising/ })).toBeTruthy()
  })

  it('saves the edited list against the bill with replace=true', async () => {
    renderAt({ itemiseBill: ITEMISED_BILL })
    await screen.findByText('Soap')
    fireEvent.click(screen.getByRole('button', { name: 'Remove Item 1' }))
    fireEvent.change(screen.getByPlaceholderText('Category'), { target: { value: 'Food' } })
    fireEvent.change(screen.getByPlaceholderText('Amount'), { target: { value: '40' } })
    fireEvent.click(screen.getByRole('button', { name: /Add item/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Submit bill/ }))
    await waitFor(() => expect(client.createExpensesBulk).toHaveBeenCalled())
    const [items, billId, options] = client.createExpensesBulk.mock.calls[0]
    expect(billId).toBe(88)
    expect(options).toEqual({ replace: true })
    expect(items.map((i) => [i.description, i.amount, i.shop])).toEqual([['Soap', 60, 'ICA Nära'], ['', 40, 'ICA Nära']])
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull()) // leaves bill mode afterwards
  })

  it('a first-time itemise does not ask for replacement', async () => {
    renderAt({ itemiseBill: { ...BILL, status: 'pending' } })
    await screen.findByRole('status')
    await addItem(35.91)
    fireEvent.click(await screen.findByRole('button', { name: /Submit bill/ }))
    await waitFor(() => expect(client.createExpensesBulk).toHaveBeenCalled())
    expect(client.createExpensesBulk.mock.calls[0][2]).toBeUndefined()
  })

  it('moves an item back into the form to change it', async () => {
    renderAt({ itemiseBill: ITEMISED_BILL })
    await screen.findByText('Soap')
    fireEvent.click(screen.getByRole('button', { name: 'Edit Soap' }))
    expect(screen.queryByText('Soap')).toBeNull() // taken out of the list...
    expect(screen.getByPlaceholderText('Category').value).toBe('Household') // ...and into the form
    expect(screen.getByPlaceholderText('Amount').value).toBe('60')
    fireEvent.change(screen.getByPlaceholderText('Amount'), { target: { value: '55' } })
    fireEvent.click(screen.getByRole('button', { name: /Add item/ }))
    expect(await screen.findByText(/less than the receipt total/)).toBeTruthy() // 40 + 55 = 95 vs 100
  })

  it('shows an error and stays out of bill mode if the items cannot be loaded', async () => {
    client.fetchBillItems.mockRejectedValueOnce(new Error('Bill not found'))
    renderAt({ itemiseBill: ITEMISED_BILL })
    await waitFor(() => expect(setError).toHaveBeenCalledWith('Bill not found'))
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('cancelling leaves the bill untouched', async () => {
    renderAt({ itemiseBill: ITEMISED_BILL })
    await screen.findByText('Soap')
    fireEvent.click(within(screen.getByRole('status')).getByRole('button', { name: 'Cancel' }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await waitFor(() => expect(client.createExpensesBulk).not.toHaveBeenCalled())
  })
})

describe('"Edit items" on an itemised bill group', () => {
  beforeEach(() => {
    client.fetchBillItems.mockImplementation(async () => [ITEM(1)])
    client.fetchBill.mockImplementation(async () => ITEMISED_BILL)
  })

  it('is on the header of a group of items from one itemised bill, and opens it for editing', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [ITEM(1), ITEM(2)], total: 2 }))
    renderAt(undefined)
    const head = await header('ICA Nära')
    expect(head.className).not.toContain('row-total-only')
    fireEvent.click(within(head).getByRole('button', { name: 'Edit items' }))
    const banner = await screen.findByRole('status')
    expect(client.fetchBill).toHaveBeenCalledWith(88)
    expect(within(banner).getByText(/Editing items: ICA Nära/)).toBeTruthy()
    expect(head.textContent).toContain('▸') // the click did not also expand the group
  })

  it.each([
    ['an ordinary group with no bill', [ITEM(1, { source_bill_id: null })]],
    ['a group that mixes two bills', [ITEM(1), ITEM(2, { source_bill_id: 99 })]],
    ['a group that includes a total-only line', [ITEM(1), ITEM(2, { bill_total_only: true })]],
  ])('is not offered for %s', async (_, items) => {
    client.fetchExpenses.mockImplementation(async () => ({ items, total: items.length }))
    renderAt(undefined)
    const head = await header('ICA Nära')
    expect(within(head).queryByRole('button', { name: 'Edit items' })).toBeNull()
  })

  it('reports a failure to load the bill', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [ITEM(1)], total: 1 }))
    client.fetchBill.mockRejectedValueOnce(new Error('Bill not found'))
    renderAt(undefined)
    fireEvent.click(within(await header('ICA Nära')).getByRole('button', { name: 'Edit items' }))
    await waitFor(() => expect(setError).toHaveBeenCalledWith('Bill not found'))
    expect(screen.queryByRole('status')).toBeNull()
  })
})

describe('names of bill groups on the Expenses page', () => {
  const line = (id, extra) => ({ ...NORMAL, id, shop: '', description: `Item ${id}`, source_bill_id: 500 + id, ...extra })

  it('a single line with no shop is named after what it is (like on the Bills page)', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [line(1, { description: 'Bus ticket' })], total: 1 }))
    renderAt(undefined)
    expect(await header('Bus ticket')).toBeTruthy()
  })

  it('a group with a shop uses the shop, whatever the lines are called', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [line(1, { shop: 'ICA Maxi' }), line(2, { shop: 'ICA Maxi', source_bill_id: 501 })], total: 2 }))
    renderAt(undefined)
    expect(await header('ICA Maxi')).toBeTruthy()
  })

  it('shop-less lines are never merged: each is its own bill, named after itself (as on the Bills page)', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [line(1, { group_id: 3 }), line(2, { group_id: 3 })], total: 2 }))
    renderAt(undefined)
    const first = await header('Item 1')
    const second = await header('Item 2')
    expect(first).not.toBe(second)
    expect(first.textContent).toMatch(/1 item ·/)
    expect(second.textContent).toMatch(/1 item ·/)
  })
})


describe('Add expense form labels', () => {
  it('calls the description "Item name" and offers Unit as a dropdown', async () => {
    client.fetchExpenses.mockResolvedValue({ items: [], total: 0 })
    renderAt()
    expect(screen.getByPlaceholderText('Item name')).toBeTruthy()
    expect(screen.queryByPlaceholderText('Description')).toBeNull()
    expect(screen.queryAllByText('Description')).toHaveLength(0)
    const unit = screen.getAllByRole('combobox', { name: 'Unit' })[0]
    expect([...unit.options].map((o) => o.value)).toEqual(expect.arrayContaining(['Count', 'Kg', 'Litre']))
    expect(screen.getByText('Quantity')).toBeTruthy()
  })
})

describe('importing and exporting live elsewhere', () => {
  it('has no import form and no export buttons (Import page and Settings own those)', async () => {
    renderAt()
    await waitFor(() => expect(client.fetchExpenses).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Export CSV' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Export Excel' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Import' })).toBeNull()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(screen.queryByText(/Skipped rows/)).toBeNull()
  })
})

describe('editing an expense in the list', () => {
  it('opens a labelled, full-width panel instead of squeezed table cells', async () => {
    renderAt(undefined)
    await flatView()
    await screen.findByText('Milk')
    fireEvent.click(within(rowOf('Milk')).getByTitle('Edit'))
    const panel = document.querySelector('tr.editing')
    expect(panel).toBeTruthy()
    expect(panel.querySelectorAll('td')).toHaveLength(1) // one cell spanning the table
    for (const label of ['Date', 'Category', 'Subcategory', 'Shop', 'Item name', 'Quantity', 'Unit', 'Amount', 'Currency']) {
      expect(within(panel).getByLabelText(label)).toBeTruthy()
    }
    expect(within(panel).getByLabelText('Item name').value).toBe('Milk')
    expect(within(panel).getByTitle('Save')).toBeTruthy()
    fireEvent.click(within(panel).getByTitle('Cancel'))
    expect(document.querySelector('tr.editing')).toBeNull()
  })
})

describe('editing a single-expense bill straight from its header', () => {
  it('edits a total-only expense (rent, an Airbnb stay…) without itemising it', async () => {
    client.updateExpense.mockResolvedValue({})
    renderAt(undefined)
    const bill = await header('LIDL145MALMOBA')
    expect(document.querySelector('tr.editing')).toBeNull()
    fireEvent.click(within(bill).getByRole('button', { name: 'Edit LIDL145MALMOBA' }))
    const panel = document.querySelector('tr.editing') // the bill opened and the editor is in it
    expect(panel).toBeTruthy()
    expect(within(panel).getByLabelText('Category').value).toBe('Bills')
    fireEvent.change(within(panel).getByLabelText('Category'), { target: { value: 'Housing' } })
    fireEvent.change(within(panel).getByLabelText('Amount'), { target: { value: '36.5' } })
    fireEvent.click(within(panel).getByTitle('Save'))
    await waitFor(() => expect(client.updateExpense).toHaveBeenCalledTimes(1))
    const [id, body] = client.updateExpense.mock.calls[0]
    expect(id).toBe(2)
    expect(body).toMatchObject({ category: 'Housing', amount: 36.5, group_id: null, date: '2026-07-21' })
    await waitFor(() => expect(loadAll).toHaveBeenCalled())
  })

  it('can put it in a trip while editing', async () => {
    spaces = { trips: [{ id: 7, name: 'Goa', space_type: 'trip', role: 'owner' }], groups: [] }
    client.updateExpense.mockResolvedValue({})
    renderAt(undefined)
    const bill = await header('LIDL145MALMOBA')
    fireEvent.click(within(bill).getByRole('button', { name: 'Edit LIDL145MALMOBA' }))
    const panel = document.querySelector('tr.editing')
    fireEvent.change(within(panel).getByLabelText('Space'), { target: { value: '7' } })
    fireEvent.click(within(panel).getByTitle('Save'))
    await waitFor(() => expect(client.updateExpense).toHaveBeenCalled())
    expect(client.updateExpense.mock.calls[0][1]).toMatchObject({ group_id: 7 })
  })

  it('is not offered on a bill with several items (open the bill and edit an item)', async () => {
    client.fetchExpenses.mockImplementation(async () => ({
      items: [
        { ...NORMAL, id: 1, shop: 'ICA', description: 'Milk' },
        { ...NORMAL, id: 3, shop: 'ICA', description: 'Bread' },
      ],
      total: 2,
    }))
    renderAt(undefined)
    const bill = await header('ICA')
    expect(within(bill).queryByRole('button', { name: /^Edit / })).toBeNull()
  })

  it('is not offered when you may not edit the expense (viewer in that space)', async () => {
    spaces = { trips: [], groups: [{ id: 3, name: 'Home', space_type: 'household', role: 'viewer' }] }
    client.fetchExpenses.mockImplementation(async () => ({ items: [{ ...TOTAL_ONLY, group_id: 3 }], total: 1 }))
    renderAt(undefined)
    const bill = await header('LIDL145MALMOBA')
    expect(within(bill).queryByRole('button', { name: /^Edit / })).toBeNull()
  })
})

const lastFetch = () => client.fetchExpenses.mock.calls.at(-1)[0]

describe('date filter', () => {
  const pick = (value) => fireEvent.change(screen.getByTitle('Show expenses from…'), { target: { value } })

  it('is "any date" until a period is chosen', async () => {
    renderAt(undefined)
    await screen.findByTitle('Show expenses from…')
    expect(lastFetch().date_from).toBe('')
    expect(lastFetch().date_to).toBe('')
  })

  it('asks for exactly one month', async () => {
    renderAt(undefined)
    await screen.findByTitle('Show expenses from…')
    pick('pick_month')
    fireEvent.change(await screen.findByLabelText('Month'), { target: { value: '2026-02' } })
    await waitFor(() => expect(lastFetch()).toMatchObject({ date_from: '2026-02-01', date_to: '2026-02-28', page: 1 }))
  })

  it('asks for exactly one year', async () => {
    renderAt(undefined)
    await screen.findByTitle('Show expenses from…')
    pick('pick_year')
    fireEvent.change(await screen.findByLabelText('Year'), { target: { value: '2025' } })
    await waitFor(() => expect(lastFetch()).toMatchObject({ date_from: '2025-01-01', date_to: '2025-12-31' }))
  })

  it('still offers a custom range', async () => {
    renderAt(undefined)
    await screen.findByTitle('Show expenses from…')
    pick('custom')
    fireEvent.change(await screen.findByLabelText('From date'), { target: { value: '2026-03-05' } })
    fireEvent.change(screen.getByLabelText('To date'), { target: { value: '2026-04-10' } })
    await waitFor(() => expect(lastFetch()).toMatchObject({ date_from: '2026-03-05', date_to: '2026-04-10' }))
  })

  it('Clear filters goes back to any date', async () => {
    renderAt(undefined)
    await screen.findByTitle('Show expenses from…')
    pick('last_year')
    await waitFor(() => expect(lastFetch().date_from).toBe(`${new Date().getFullYear() - 1}-01-01`))
    fireEvent.click(await screen.findByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(lastFetch().date_from).toBe(''))
    expect(screen.getByTitle('Show expenses from…').value).toBe('')
  })
})

describe('the ✈ trip button on a bill or an expense', () => {
  const GOA = { id: 7, name: 'Goa', space_type: 'trip', role: 'owner' }
  const OSLO = { id: 8, name: 'Oslo', space_type: 'trip', role: 'viewer' }
  const panel = () => screen.getByRole('region', { name: 'Move or copy to a trip' })
  const choose = (value) => fireEvent.change(within(panel()).getByLabelText('Trip or space'), { target: { value } })

  beforeEach(() => {
    spaces = { trips: [GOA, OSLO], groups: [] }
    client.bulkUpdateExpenses.mockResolvedValue({ updated: 1 })
    client.bulkCopyExpenses.mockResolvedValue({ copied: 1, skipped: 0 })
  })

  it('moves one expense into the chosen trip', async () => {
    renderAt(undefined)
    await flatView()
    fireEvent.click(await screen.findByLabelText('Move or copy Milk to a trip'))
    expect(within(panel()).getByText(/Milk · 1 item$/)).toBeTruthy()
    expect(within(panel()).getByRole('button', { name: 'Move' }).disabled).toBe(true) // no trip chosen yet
    choose('7')
    fireEvent.click(within(panel()).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalledWith({ ids: [1], changes: { group_id: 7 } }))
    expect(await screen.findByText('Moved 1 expense to Goa.')).toBeTruthy()
    expect(screen.queryByRole('region', { name: 'Move or copy to a trip' })).toBeNull() // closes when done
    expect(loadAll).toHaveBeenCalled()
  })

  it('copies one expense and leaves the original', async () => {
    renderAt(undefined)
    await flatView()
    fireEvent.click(await screen.findByLabelText('Move or copy Milk to a trip'))
    choose('7')
    fireEvent.click(within(panel()).getByRole('button', { name: 'Copy' }))
    await waitFor(() => expect(client.bulkCopyExpenses).toHaveBeenCalledWith({ ids: [1], group_id: 7 }))
    expect(client.bulkUpdateExpenses).not.toHaveBeenCalled()
    expect(await screen.findByText('Copied 1 expense to Goa.')).toBeTruthy()
  })

  it('can send an expense back to personal, but not copy it there', async () => {
    renderAt(undefined)
    await flatView()
    fireEvent.click(await screen.findByLabelText('Move or copy Milk to a trip'))
    choose('personal')
    expect(within(panel()).getByRole('button', { name: 'Copy' }).disabled).toBe(true)
    fireEvent.click(within(panel()).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalledWith({ ids: [1], changes: { group_id: null } }))
    expect(await screen.findByText('Moved 1 expense to personal expenses.')).toBeTruthy()
  })

  it('moves a whole bill from its header', async () => {
    renderAt(undefined)
    const bill = await header('LIDL145MALMOBA')
    fireEvent.click(within(bill).getByRole('button', { name: /Move or copy LIDL145MALMOBA to a trip/ }))
    choose('7')
    fireEvent.click(within(panel()).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalledWith({ ids: [2], changes: { group_id: 7 } }))
  })

  it('offers trips first, never one where you are only a viewer, and Cancel closes it', async () => {
    renderAt(undefined)
    await flatView()
    fireEvent.click(await screen.findByLabelText('Move or copy Milk to a trip'))
    const options = [...within(panel()).getByLabelText('Trip or space').querySelectorAll('option')].map((o) => o.textContent)
    expect(options.some((o) => o.includes('Goa'))).toBe(true)
    expect(options.some((o) => o.includes('Oslo'))).toBe(false)
    fireEvent.click(within(panel()).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('region', { name: 'Move or copy to a trip' })).toBeNull()
  })

  it('shows the server’s message and keeps the panel open when the move fails', async () => {
    client.bulkUpdateExpenses.mockRejectedValue(new Error('Not allowed'))
    renderAt(undefined)
    await flatView()
    fireEvent.click(await screen.findByLabelText('Move or copy Milk to a trip'))
    choose('7')
    fireEvent.click(within(panel()).getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(setError).toHaveBeenCalledWith('Not allowed'))
    expect(panel()).toBeTruthy()
  })

  it('is not shown when there is no trip or space to put it in', async () => {
    spaces = { trips: [], groups: [] }
    renderAt(undefined)
    await flatView()
    await screen.findByText('Milk')
    expect(screen.queryByLabelText('Move or copy Milk to a trip')).toBeNull()
  })
})

describe('editing expenses together', () => {
  const start = async () => {
    renderAt(undefined)
    await flatView()
    await screen.findByText('Milk')
    fireEvent.click(screen.getByRole('button', { name: /Edit together/ }))
  }
  const fill = (label, value) => fireEvent.change(within(screen.getByTestId('bulk-bar')).getByLabelText(label), { target: { value } })

  beforeEach(() => client.bulkUpdateExpenses.mockResolvedValue({ updated: 1 }))

  it('changes only what is filled in, on only the ticked expenses', async () => {
    await start()
    expect(screen.getByTestId('bulk-count').textContent).toContain('Nothing selected yet')
    expect(screen.getByRole('button', { name: /Apply to 0/ }).disabled).toBe(true)
    fireEvent.click(screen.getByLabelText('Select Milk'))
    expect(screen.getByTestId('bulk-count').textContent).toContain('1 selected')
    expect(screen.getByRole('button', { name: /Apply to 1/ }).disabled).toBe(true) // nothing to change yet
    fill('Category', ' Groceries ')
    expect(screen.getByTestId('bulk-summary').textContent).toBe('Will set Category → Groceries on 1 expense.')
    fireEvent.click(screen.getByRole('button', { name: /Apply to 1 expense/ }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalledTimes(1))
    expect(client.bulkUpdateExpenses).toHaveBeenCalledWith({ ids: [1], changes: { category: 'Groceries' } })
    expect(await screen.findByText('Updated 1 expense.')).toBeTruthy()
    expect(loadAll).toHaveBeenCalled() // the dashboard and other pages follow
    expect(screen.getByTestId('bulk-count').textContent).toContain('Nothing selected yet') // selection is cleared
  })

  describe('copying to a space', () => {
    const GOA = { id: 7, name: 'Goa', space_type: 'trip', role: 'owner' }
    const OSLO = { id: 8, name: 'Oslo', space_type: 'trip', role: 'viewer' }
    const copyBtn = (n) => within(screen.getByTestId('bulk-bar')).getByRole('button', { name: new RegExp(`Copy ${n} expense`) })
    beforeEach(() => {
      spaces = { trips: [GOA, OSLO], groups: [] }
      client.bulkCopyExpenses.mockResolvedValue({ copied: 1, skipped: 0 })
    })

    it('copies only the ticked expenses into the chosen space and keeps the originals', async () => {
      await start()
      expect(copyBtn(0).disabled).toBe(true)
      fireEvent.click(screen.getByLabelText('Select Milk'))
      expect(copyBtn(1).disabled).toBe(true) // no space chosen yet
      fill('Copy to space', '7')
      fireEvent.click(copyBtn(1))
      await waitFor(() => expect(client.bulkCopyExpenses).toHaveBeenCalledWith({ ids: [1], group_id: 7 }))
      expect(client.bulkUpdateExpenses).not.toHaveBeenCalled()
      expect(await screen.findByText('Copied 1 expense to Goa.')).toBeTruthy()
      expect(loadAll).toHaveBeenCalled()
      expect(screen.getByTestId('bulk-count').textContent).toContain('Nothing selected yet')
    })

    it('does not offer a space where you are only a viewer', async () => {
      await start()
      const options = [...within(screen.getByTestId('bulk-bar')).getByLabelText('Copy to space').querySelectorAll('option')].map((o) => o.textContent)
      expect(options.some((o) => o.includes('Goa'))).toBe(true)
      expect(options.some((o) => o.includes('Oslo'))).toBe(false)
    })

    it('says how many were skipped because they were already there', async () => {
      client.bulkCopyExpenses.mockResolvedValue({ copied: 0, skipped: 1 })
      await start()
      fireEvent.click(screen.getByLabelText('Select Milk'))
      fill('Copy to space', '7')
      fireEvent.click(copyBtn(1))
      expect(await screen.findByText('Copied 0 expenses to Goa. 1 already there, skipped.')).toBeTruthy()
    })
  })

  it('the header box selects every row on the page', async () => {
    await start()
    fireEvent.click(screen.getByLabelText('Select all on this page'))
    expect(screen.getByTestId('bulk-count').textContent).toContain('2 selected')
    fill('Shop', 'Unionen')
    fill('Item name', 'Membership')
    fireEvent.click(screen.getByRole('button', { name: /Apply to 2 expenses/ }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalled())
    expect(client.bulkUpdateExpenses).toHaveBeenCalledWith({ ids: [1, 2], changes: { shop: 'Unionen', description: 'Membership' } })
  })

  it('a bill header ticks all of its items', async () => {
    renderAt(undefined)
    await screen.findByText(/· Milk ·/)
    fireEvent.click(screen.getByRole('button', { name: /Edit together/ }))
    fireEvent.click(screen.getByLabelText('Select Milk'))
    expect(screen.getByTestId('bulk-count').textContent).toContain('1 selected')
  })

  it('can offer to select everything that matches, beyond this page', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [NORMAL, TOTAL_ONLY], total: 9 }))
    await start()
    expect(screen.queryByRole('button', { name: /Select all 9 matching/ })).toBeNull()
    fireEvent.click(screen.getByLabelText('Select all on this page'))
    fireEvent.click(screen.getByRole('button', { name: 'Select all 9 matching' }))
    expect(screen.getByTestId('bulk-count').textContent).toContain('All 9 matching expenses are selected.')
    fill('Category', 'Membership')
    client.bulkUpdateExpenses.mockResolvedValue({ updated: 9 })
    fireEvent.click(screen.getByRole('button', { name: /Apply to 9 expenses/ }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalled())
    const body = client.bulkUpdateExpenses.mock.calls[0][0]
    expect(body.ids).toBeUndefined()
    expect(body.changes).toEqual({ category: 'Membership' })
    expect(body.filters).toMatchObject({ search: undefined, date_from: undefined })
    expect(await screen.findByText('Updated 9 expenses.')).toBeTruthy()
  })

  it('applies the current search and date filter when everything matching is selected', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [NORMAL, TOTAL_ONLY], total: 9 }))
    await start()
    fireEvent.change(screen.getByPlaceholderText('Search item, shop, brand…'), { target: { value: 'union' } })
    fireEvent.change(screen.getByTitle('Show expenses from…'), { target: { value: 'this_year' } })
    await waitFor(() => expect(lastFetch().search).toBe('union'))
    fireEvent.click(await screen.findByLabelText('Select all on this page'))
    fireEvent.click(screen.getByRole('button', { name: 'Select all 9 matching' }))
    fill('Category', 'Membership')
    fireEvent.click(screen.getByRole('button', { name: /Apply to 9 expenses/ }))
    await waitFor(() => expect(client.bulkUpdateExpenses).toHaveBeenCalled())
    const year = new Date().getFullYear()
    expect(client.bulkUpdateExpenses.mock.calls[0][0].filters).toMatchObject({
      search: 'union', date_from: `${year}-01-01`, date_to: `${year}-12-31`,
    })
  })

  it('unticking one row while everything matching is selected narrows it to the page', async () => {
    client.fetchExpenses.mockImplementation(async () => ({ items: [NORMAL, TOTAL_ONLY], total: 9 }))
    await start()
    fireEvent.click(screen.getByLabelText('Select all on this page'))
    fireEvent.click(screen.getByRole('button', { name: 'Select all 9 matching' }))
    fireEvent.click(screen.getByLabelText('Select Milk'))
    expect(screen.getByTestId('bulk-count').textContent).toContain('1 selected')
  })

  it('changing the filter starts the selection over', async () => {
    await start()
    fireEvent.click(screen.getByLabelText('Select Milk'))
    fireEvent.change(screen.getByTitle('Show expenses from…'), { target: { value: 'this_year' } })
    await waitFor(() => expect(screen.getByTestId('bulk-count').textContent).toContain('Nothing selected yet'))
  })

  it('shows the error and keeps the selection if the server refuses', async () => {
    client.bulkUpdateExpenses.mockRejectedValueOnce(new Error('Viewers can\'t add or edit expenses in this space'))
    await start()
    fireEvent.click(screen.getByLabelText('Select Milk'))
    fill('Category', 'X')
    fireEvent.click(screen.getByRole('button', { name: /Apply to 1 expense/ }))
    await waitFor(() => expect(setError).toHaveBeenCalledWith("Viewers can't add or edit expenses in this space"))
    expect(screen.getByTestId('bulk-count').textContent).toContain('1 selected')
  })

  it('leaving edit-together hides the boxes and the bar', async () => {
    await start()
    fireEvent.click(screen.getByRole('button', { name: /Stop editing together/ }))
    expect(screen.queryByTestId('bulk-bar')).toBeNull()
    expect(screen.queryByLabelText('Select Milk')).toBeNull()
  })
})

describe('ExpensesPage inside Spending (embedded)', () => {
  it('hides its own title and starts as a flat list of items', async () => {
    loadAll = vi.fn()
    setError = vi.fn()
    function Embedded() {
      const e = useExpenseHandlers(loadAll, setError)
      return (
        <ExpensesPage
          embedded form={e.form} setForm={e.setForm} saving={e.saving} onAdd={e.handleAdd} onAddBill={e.handleAddBill}
          editingId={e.editingId} editForm={e.editForm} setEditForm={e.setEditForm} startEdit={e.startEdit}
          cancelEdit={e.cancelEdit} saveEdit={e.saveEdit} onDelete={e.handleDelete} options={OPTIONS}
          onBulkUpdate={e.handleBulkUpdate} trips={[]} groups={[]} onError={setError}
        />
      )
    }
    render(
      <MemoryRouter initialEntries={['/spending?view=items']}>
        <Embedded />
      </MemoryRouter>,
    )
    await waitFor(() => expect(client.fetchExpenses).toHaveBeenCalled())
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })
})

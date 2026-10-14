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
        onImport={e.handleImport} onExport={e.handleExport} importCurrency={e.importCurrency}
        setImportCurrency={e.setImportCurrency} onAddRow={e.handleAddRow} trips={[]} groups={[]} onError={setError}
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

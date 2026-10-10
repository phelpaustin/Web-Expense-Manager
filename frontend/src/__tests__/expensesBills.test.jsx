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
    const ordinary = await header('No shop')
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
    await header('No shop')
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
    await header('No shop')
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByRole('button', { name: /Add by bill/ })).toBeTruthy()
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { useBillsHandlers, billForItemising, DEFAULT_QUERY } from '../hooks/useBillsHandlers.js'

const COUNTS = { pending: 2, total_only: 1, itemised: 0, all: 3 }
const page = (items, extra = {}) => ({ items, total: items.length, page: 1, page_size: 25, counts: COUNTS, ...extra })
const BILL = (id, extra = {}) => ({ id, date: '2026-07-21', shop: `Shop ${id}`, amount: 10, currency: 'SEK', status: 'pending', has_receipt: false, ...extra })

let loadAll, setError, setOptions, navigate
const setup = async (enabled = true) => {
  const hook = renderHook(() => useBillsHandlers(loadAll, setError, setOptions, navigate, enabled))
  await waitFor(() => expect(hook.result.current.loading).toBe(false))
  return hook
}
const lastParams = () => client.fetchBills.mock.calls.at(-1)[0]

// Flows now ask through in-app dialogs. Start the action, answer the dialog that opens, finish it.
async function withDialog(result, start, answer) {
  let promise
  await act(async () => { promise = start() })
  await waitFor(() => expect(result.current.dialog).not.toBeNull())
  const opened = result.current.dialog
  act(() => result.current.closeDialog(answer))
  await act(async () => { await promise })
  return opened
}

beforeEach(() => {
  loadAll = vi.fn(async () => {})
  setError = vi.fn()
  setOptions = vi.fn()
  navigate = vi.fn()
  client.fetchBills.mockImplementation(async () => page([BILL(1), BILL(2)]))
})
afterEach(() => vi.restoreAllMocks())

describe('syncing (listing bills never writes)', () => {
  it('asks for one sync when the list says needs_sync, then reloads', async () => {
    client.fetchBills
      .mockResolvedValueOnce({ ...page([]), needs_sync: true })
      .mockResolvedValueOnce({ ...page([BILL(1)]), needs_sync: false })
    client.syncBills.mockResolvedValue({ changed: true })
    const { result } = await setup()
    expect(client.syncBills).toHaveBeenCalledTimes(1)
    expect(client.fetchBills).toHaveBeenCalledTimes(2)
    expect(result.current.data.items.map((b) => b.id)).toEqual([1])
  })

  it('does not sync when nothing is due', async () => {
    await setup()
    expect(client.syncBills).not.toHaveBeenCalled()
  })

  it('syncs at most once per load even if the flag stays on', async () => {
    client.fetchBills.mockResolvedValue({ ...page([BILL(1)]), needs_sync: true })
    client.syncBills.mockResolvedValue({ changed: false })
    await setup()
    expect(client.syncBills).toHaveBeenCalledTimes(1)
    expect(client.fetchBills).toHaveBeenCalledTimes(2)
  })

  it('shows the list it already has when the sync fails', async () => {
    client.fetchBills.mockResolvedValue({ ...page([BILL(1)]), needs_sync: true })
    client.syncBills.mockRejectedValue(new Error('nope'))
    const { result } = await setup()
    expect(result.current.data.items.map((b) => b.id)).toEqual([1])
    expect(setError).not.toHaveBeenCalled()
  })
})

describe('loading', () => {
  it('loads the first page of to-itemise bills once signed in', async () => {
    const { result } = await setup()
    expect(client.fetchBills).toHaveBeenCalledTimes(1)
    expect(lastParams()).toEqual(DEFAULT_QUERY)
    expect(result.current.data.items.map((b) => b.id)).toEqual([1, 2])
    expect(result.current.data.counts).toEqual(COUNTS)
  })

  it('does nothing before sign-in (no 401 on the login screen)', async () => {
    renderHook(() => useBillsHandlers(loadAll, setError, setOptions, navigate, false))
    await act(async () => {})
    expect(client.fetchBills).not.toHaveBeenCalled()
  })

  it('reloads on the first page when the tab, search or sort changes', async () => {
    const { result } = await setup()
    await act(async () => { result.current.setQuery({ page: 3 }) })
    await waitFor(() => expect(lastParams().page).toBe(3))
    await act(async () => { result.current.setQuery({ status: 'itemised' }) })
    await waitFor(() => expect(lastParams()).toMatchObject({ status: 'itemised', page: 1 }))
    await act(async () => { result.current.setQuery({ q: 'lidl', sort: 'shop' }) })
    await waitFor(() => expect(lastParams()).toMatchObject({ q: 'lidl', sort: 'shop', page: 1 }))
  })

  it('reports a load failure without crashing', async () => {
    client.fetchBills.mockRejectedValueOnce(new Error('boom'))
    await setup()
    expect(setError).toHaveBeenCalledWith('boom')
  })

  it('steps back a page when the current one is empty after a delete', async () => {
    client.fetchBills.mockImplementation(async (q) => (q.page === 2 ? { ...page([]), total: 25, page: 2 } : page([BILL(1)], { total: 25 })))
    const { result } = await setup()
    await act(async () => { result.current.setQuery({ page: 2 }) })
    await waitFor(() => expect(lastParams().page).toBe(1))
    expect(result.current.query.page).toBe(1)
  })
})

describe('selection', () => {
  it('toggles, selects the page and clears', async () => {
    const { result } = await setup()
    act(() => result.current.toggleSelect(1))
    expect([...result.current.selected]).toEqual([1])
    act(() => result.current.toggleSelect(1))
    expect(result.current.selected.size).toBe(0)
    act(() => result.current.selectPage())
    expect([...result.current.selected].sort()).toEqual([1, 2])
    act(() => result.current.clearSelection())
    expect(result.current.selected.size).toBe(0)
  })

  it('keeps the selection across pages but drops it when the tab or search changes', async () => {
    const { result } = await setup()
    act(() => result.current.toggleSelect(1))
    await act(async () => { result.current.setQuery({ page: 2 }) })
    expect(result.current.selected.has(1)).toBe(true)
    await act(async () => { result.current.setQuery({ status: 'total_only' }) })
    expect(result.current.selected.size).toBe(0)
  })
})

describe('uploading a receipt', () => {
  const file = new File(['x'], 'lidl.pdf', { type: 'application/pdf' })

  it('only stores the file: no questions, no values read from it', async () => {
    client.uploadBill.mockResolvedValueOnce({ result: 'created', bill: BILL(8, { status: 'pending', amount: 0 }) })
    const { result } = await setup()
    await act(async () => { await result.current.actions.uploadBill(file) })
    expect(client.uploadBill).toHaveBeenCalledTimes(1)
    expect(client.uploadBill).toHaveBeenCalledWith(file)
    expect(result.current.dialog).toBeFalsy()
    expect(result.current.notice.text).toMatch(/under “To itemise”/)
    expect(result.current.notice.text).toMatch(/Nothing is counted as spending/)
    expect(result.current.query.status).toBe('pending')
  })

  it('still says so when the bill was recorded as a total', async () => {
    client.uploadBill.mockResolvedValueOnce({ result: 'created', bill: BILL(1, { status: 'total_only', amount: 12 }) })
    const { result } = await setup()
    await act(async () => { await result.current.actions.uploadBill(file) })
    expect(result.current.notice.text).toMatch(/counted as spending/)
  })

  it('reports a failed upload', async () => {
    client.uploadBill.mockRejectedValueOnce(new Error('File too large (max 10 MB)'))
    const { result } = await setup()
    await act(async () => { await result.current.actions.uploadBill(file) })
    expect(setError).toHaveBeenCalledWith('File too large (max 10 MB)')
  })
})

describe('recording totals, undoing, deleting', () => {
  it('records a bill with the chosen category and refreshes the totals', async () => {
    const { result } = await setup()
    await act(async () => { await result.current.actions.recordTotal(BILL(1), 'Groceries') })
    expect(client.recordBillTotal).toHaveBeenCalledWith(1, { category: 'Groceries', amount: undefined })
    expect(loadAll).toHaveBeenCalled() // budgets/dashboard include the new total
    expect(client.fetchBills.mock.calls.length).toBeGreaterThan(1)
  })

  it('asks for the amount in a dialog when the bill has none', async () => {
    const { result } = await setup()
    const dialog = await withDialog(result, () => result.current.actions.recordTotal(BILL(1, { amount: 0 }), 'Bills'), 42.5)
    expect(dialog).toMatchObject({ kind: 'amount', currency: 'SEK' })
    expect(dialog.message).toMatch(/Shop 1/)
    expect(client.recordBillTotal).toHaveBeenCalledWith(1, { category: 'Bills', amount: 42.5 })
  })

  it('does nothing if that dialog is cancelled', async () => {
    const { result } = await setup()
    await withDialog(result, () => result.current.actions.recordTotal(BILL(1, { amount: 0 }), 'Bills'), null)
    expect(client.recordBillTotal).not.toHaveBeenCalled()
    expect(setError).not.toHaveBeenCalled()
  })

  it('does not ask when the bill already has an amount', async () => {
    const { result } = await setup()
    await act(async () => { await result.current.actions.recordTotal(BILL(1), 'Bills') })
    expect(result.current.dialog).toBeNull()
  })

  it('bulk-records the selection, reports skips and clears the selection', async () => {
    client.recordBillTotals.mockResolvedValueOnce({ recorded: 2, skipped: [{ id: 9, reason: 'Possible duplicate: review it first' }] })
    const { result } = await setup()
    act(() => { result.current.toggleSelect(1); result.current.toggleSelect(2); result.current.toggleSelect(9) })
    await act(async () => { await result.current.actions.bulkRecord('Food') })
    expect(client.recordBillTotals).toHaveBeenCalledWith([1, 2, 9], 'Food')
    expect(result.current.notice.text).toBe('Recorded 2 bills as spending, skipped 1.')
    expect(result.current.notice.details).toEqual(['Possible duplicate: review it first'])
    expect(result.current.selected.size).toBe(0)
    expect(loadAll).toHaveBeenCalled()
  })

  it('undoes a recorded total', async () => {
    const { result } = await setup()
    await act(async () => { await result.current.actions.undo(BILL(2, { status: 'total_only' })) })
    expect(client.undoBillTotal).toHaveBeenCalledWith(2)
    expect(loadAll).toHaveBeenCalled()
  })

  it('only deletes after you confirm', async () => {
    const { result } = await setup()
    const dialog = await withDialog(result, () => result.current.actions.remove(BILL(1)), false)
    expect(dialog).toMatchObject({ kind: 'confirm', danger: true, confirmLabel: 'Delete bill' })
    expect(client.deletePendingBill).not.toHaveBeenCalled()
    await withDialog(result, () => result.current.actions.remove(BILL(1)), true)
    expect(client.deletePendingBill).toHaveBeenCalledWith(1)
  })

  it('tells you expenses are kept when deleting an itemised bill', async () => {
    const { result } = await setup()
    const dialog = await withDialog(result, () => result.current.actions.remove(BILL(3, { status: 'itemised' })), false)
    expect(dialog.message).toMatch(/expenses made from it are kept/)
  })

  it('bulk-deletes after confirming and reports skipped total-only bills', async () => {
    client.bulkDeleteBills.mockResolvedValueOnce({ deleted: 1, skipped: [{ id: 2, reason: 'Undo the recorded total first' }] })
    const { result } = await setup()
    act(() => { result.current.toggleSelect(1); result.current.toggleSelect(2) })
    const dialog = await withDialog(result, () => result.current.actions.bulkDelete(), true)
    expect(dialog.title).toBe('Delete 2 bills?')
    expect(client.bulkDeleteBills).toHaveBeenCalledWith([1, 2])
    expect(result.current.notice.text).toBe('Deleted 1 bill, skipped 1 (undo their recorded total first).')
    expect(result.current.selected.size).toBe(0)
  })

  it('does not bulk-delete when you cancel', async () => {
    const { result } = await setup()
    act(() => result.current.toggleSelect(1))
    await withDialog(result, () => result.current.actions.bulkDelete(), false)
    expect(client.bulkDeleteBills).not.toHaveBeenCalled()
    expect(result.current.selected.size).toBe(1)
  })

  it('reports a server refusal (e.g. already itemised) instead of failing silently', async () => {
    client.recordBillTotal.mockRejectedValueOnce(new Error('This bill has already been recorded or itemised'))
    const { result } = await setup()
    await act(async () => { await result.current.actions.recordTotal(BILL(1), 'Bills') })
    expect(setError).toHaveBeenCalledWith('This bill has already been recorded or itemised')
  })
})

describe('reverting an itemised bill to a total', () => {
  const ITEMISED = BILL(3, { status: 'itemised', amount: 100, item_count: 3 })

  it('asks first, then replaces the items and refreshes the totals', async () => {
    client.revertBillToTotal.mockResolvedValueOnce({ ...ITEMISED, status: 'total_only' })
    const { result } = await setup()
    const dialog = await withDialog(result, () => result.current.actions.revertToTotal(ITEMISED, 'Groceries'), true)
    expect(dialog).toMatchObject({ kind: 'confirm', danger: true, confirmLabel: 'Revert to total' })
    expect(dialog.message).toMatch(/3 items are replaced by one line/)
    expect(client.revertBillToTotal).toHaveBeenCalledWith(3, 'Groceries')
    expect(result.current.notice.text).toMatch(/single total/)
    expect(loadAll).toHaveBeenCalled()
  })

  it('does nothing if you cancel', async () => {
    const { result } = await setup()
    await withDialog(result, () => result.current.actions.revertToTotal(ITEMISED, 'Bills'), false)
    expect(client.revertBillToTotal).not.toHaveBeenCalled()
    expect(result.current.notice).toBeNull()
  })

  it('reports a server refusal', async () => {
    client.revertBillToTotal.mockRejectedValueOnce(new Error('Only an itemised bill can be turned back into a total'))
    const { result } = await setup()
    await withDialog(result, () => result.current.actions.revertToTotal(ITEMISED, 'Bills'), true)
    expect(setError).toHaveBeenCalledWith('Only an itemised bill can be turned back into a total')
  })

  it('"Edit items" opens the Expenses page with the bill and its itemised status', async () => {
    const { result } = await setup()
    act(() => result.current.actions.itemise(ITEMISED))
    expect(navigate).toHaveBeenCalledWith('/expenses', { state: { itemiseBill: expect.objectContaining({ id: 3, status: 'itemised' }) } })
  })
})

describe('itemising later', () => {
  it('opens the Expenses page prefilled with the bill', async () => {
    const { result } = await setup()
    act(() => result.current.actions.itemise(BILL(2, { status: 'total_only', has_receipt: true, note: 'ignored', possible_duplicate: true })))
    expect(navigate).toHaveBeenCalledWith('/expenses', {
      state: { itemiseBill: { id: 2, date: '2026-07-21', shop: 'Shop 2', amount: 10, currency: 'SEK', status: 'total_only', has_receipt: true } },
    })
  })

  it('billForItemising keeps only what the Expenses page needs', () => {
    expect(Object.keys(billForItemising(BILL(1, { note: 'x', item_count: 2 }))).sort()).toEqual(
      ['amount', 'currency', 'date', 'has_receipt', 'id', 'shop', 'status'],
    )
  })
})

describe('adding a bill and receipts', () => {
  it('rejects a zero or invalid amount without calling the server', async () => {
    const { result } = await setup()
    for (const bad of ['', '0', 'abc']) {
      act(() => result.current.setForm({ date: '2026-07-21', shop: 'x', amount: bad, note: '', currency: '' }))
      await act(async () => { await result.current.actions.add({ preventDefault() {} }) })
    }
    expect(client.createPendingBill).not.toHaveBeenCalled()
    expect(setError).toHaveBeenCalledWith('Enter an amount greater than zero')
  })

  it('creates the bill, omits an unset currency and resets the form', async () => {
    const { result } = await setup()
    act(() => result.current.setForm({ date: '2026-07-21', shop: 'Coop', amount: '19.9', note: 'n', currency: '' }))
    await act(async () => { await result.current.actions.add({ preventDefault() {} }) })
    expect(client.createPendingBill).toHaveBeenCalledWith({ date: '2026-07-21', shop: 'Coop', amount: 19.9, note: 'n', currency: undefined })
    expect(result.current.form.shop).toBe('')
    expect(loadAll).toHaveBeenCalled()
  })

  it('attaches, views and removes receipts (removing asks first)', async () => {
    client.viewReceipt.mockResolvedValue(undefined)
    const { result } = await setup()
    const file = new File(['x'], 'r.pdf')
    await act(async () => { await result.current.actions.uploadReceipt(1, file) })
    expect(client.uploadReceipt).toHaveBeenCalledWith(1, file)
    act(() => result.current.actions.viewReceipt(1))
    expect(client.viewReceipt).toHaveBeenCalledWith(1)
    const dialog = await withDialog(result, () => result.current.actions.deleteReceipt(1), true)
    expect(dialog).toMatchObject({ kind: 'confirm', danger: true })
    expect(client.deleteReceipt).toHaveBeenCalledWith(1)
  })

  it('clears the duplicate warning without refreshing the dashboard', async () => {
    const { result } = await setup()
    await act(async () => { await result.current.actions.dismissDuplicate(4) })
    expect(client.dismissDuplicate).toHaveBeenCalledWith(4)
    expect(loadAll).not.toHaveBeenCalled()
  })

  it('saves the spending setting and hands the new options to the app', async () => {
    client.saveCountBillsAsSpending.mockResolvedValueOnce({ count_bills_as_spending: false })
    const { result } = await setup()
    await act(async () => { await result.current.actions.toggleCount(false) })
    expect(client.saveCountBillsAsSpending).toHaveBeenCalledWith(false)
    expect(setOptions).toHaveBeenCalledWith({ count_bills_as_spending: false })
  })
})

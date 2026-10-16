import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchBills,
  createPendingBill,
  deletePendingBill,
  bulkDeleteBills,
  recordBillTotal,
  recordBillTotals,
  undoBillTotal,
  revertBillToTotal,
  uploadReceipt,
  uploadBill,
  bulkUploadPendingBills,
  dismissDuplicate,
  viewReceipt,
  deleteReceipt,
  saveCountBillsAsSpending,
} from '../api/client.js'
import { money } from '../format.js'
import { useDialogs } from './useDialogs.js'

const EMPTY_BILL = { date: '', shop: '', amount: '', note: '', currency: '' }
export const DEFAULT_QUERY = { status: 'pending', q: '', date_from: '', date_to: '', sort: 'date_desc', page: 1, page_size: 25 }
export const EMPTY_BILLS = { items: [], total: 0, page: 1, page_size: 25, counts: { pending: 0, total_only: 0, itemised: 0, all: 0 } }

// What the Expenses page needs to start itemising a bill.
export function billForItemising(bill) {
  return {
    id: bill.id,
    date: bill.date,
    shop: bill.shop,
    amount: bill.amount,
    currency: bill.currency,
    status: bill.status,
    has_receipt: !!bill.has_receipt,
  }
}

// loadAll refreshes the dashboard/budgets/expenses totals, which change whenever a bill is
// recorded, undone or itemised. navigate opens the Expenses page to itemise a bill.
// enabled: only load once the user is signed in (otherwise the first request would be a 401).
export function useBillsHandlers(loadAll, setError, setOptions, navigate, enabled = true) {
  const [query, setQueryState] = useState(DEFAULT_QUERY)
  const [data, setData] = useState(EMPTY_BILLS)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [notice, setNotice] = useState(null)
  const [form, setForm] = useState(EMPTY_BILL)
  const dialogs = useDialogs()

  const queryRef = useRef(query)
  queryRef.current = query

  const loadBills = useCallback(
    async (q) => {
      setLoading(true)
      try {
        const res = await fetchBills(q)
        // The page may no longer exist (e.g. the last row on it was deleted): step back.
        if (res.items.length === 0 && res.total > 0 && q.page > 1) {
          setQueryState((prev) => ({ ...prev, page: Math.max(1, Math.ceil(res.total / q.page_size)) }))
          return
        }
        setData(res)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    },
    [setError],
  )

  // Load whenever the filters, tab, sort or page change.
  useEffect(() => {
    if (enabled) loadBills(query)
  }, [enabled, query, loadBills])

  // Changing the tab/search/sort goes back to page 1 and clears the selection; changing only the
  // page keeps the selection of the rows you ticked on other pages.
  const setQuery = useCallback((changes) => {
    setQueryState((prev) => {
      const next = { ...prev, ...changes }
      if (!('page' in changes)) next.page = 1
      return next
    })
    if (!('page' in changes)) setSelected(new Set())
  }, [])

  const refresh = useCallback(
    () => Promise.all([loadBills(queryRef.current), loadAll()]),
    [loadBills, loadAll],
  )

  async function run(action) {
    try {
      return await action()
    } catch (err) {
      setError(err.message)
      return undefined
    }
  }

  // ── selection ──
  const toggleSelect = (id) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const selectPage = () => setSelected((prev) => new Set([...prev, ...data.items.map((b) => b.id)]))
  const clearSelection = () => setSelected(new Set())

  // ── creating bills ──
  async function handleAdd(e) {
    e.preventDefault()
    const amount = parseFloat(form.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Enter an amount greater than zero')
      return
    }
    const created = await run(() =>
      createPendingBill({
        date: form.date,
        shop: form.shop,
        amount,
        note: form.note,
        currency: form.currency || undefined,
      }),
    )
    if (created) {
      setForm(EMPTY_BILL)
      await refresh()
    }
  }

  // The receipt is only stored; nothing is read from it. It lands in "To itemise" with no
  // amount, and you itemise it (or record its total) when you are ready.
  async function handleUploadBill(file) {
    await run(async () => {
      const res = await uploadBill(file)
      if (res.bill.status === 'total_only') {
        setNotice({ text: `Receipt added and its total of ${money(res.bill.amount, res.bill.currency)} is counted as spending. Itemise it whenever you like.` })
      } else {
        setNotice({ text: 'Receipt added under “To itemise”. Itemise it, or record its total, when you are ready. Nothing is counted as spending until you do.' })
      }
      setQuery({ status: 'pending' })
      await refresh()
    })
  }

  async function handleBulkUpload(file) {
    await run(async () => {
      const r = await bulkUploadPendingBills(file)
      const parts = [`Imported ${r.created} bill${r.created === 1 ? '' : 's'}`]
      if (r.auto_recorded > 0) parts.push(`${r.auto_recorded} counted as spending (itemise them whenever you like)`)
      if (r.possible_duplicates > 0) parts.push(`${r.possible_duplicates} possible duplicate${r.possible_duplicates === 1 ? '' : 's'} left for you to review`)
      if (r.skipped?.length > 0) parts.push(`${r.skipped.length} row${r.skipped.length === 1 ? '' : 's'} skipped`)
      setNotice({ text: `${parts.join(' · ')}.`, details: (r.skipped || []).map((s) => `Row ${s.row}: ${s.reason}`) })
      // Show what needs attention first: duplicates / nothing recorded -> the to-itemise tab.
      setQuery({ status: r.possible_duplicates > 0 || r.auto_recorded === 0 ? 'pending' : 'total_only' })
      await loadAll()
    })
  }

  // ── status changes ──
  async function handleRecordTotal(bill, category) {
    let amount
    if (!(Number(bill.amount) > 0)) {
      amount = await dialogs.promptAmount({
        title: 'Record total',
        message: `${bill.shop} (${bill.date}) has no amount yet. Enter the total to record as spending.`,
        currency: bill.currency,
        confirmLabel: 'Record total',
      })
      if (amount == null) return
    }
    const done = await run(() => recordBillTotal(bill.id, { category, amount }))
    if (done) await refresh()
  }

  async function handleBulkRecord(category) {
    const ids = [...selected]
    const r = await run(() => recordBillTotals(ids, category))
    if (!r) return
    const text =
      `Recorded ${r.recorded} bill${r.recorded === 1 ? '' : 's'} as spending` +
      (r.skipped.length > 0 ? `, skipped ${r.skipped.length}` : '') +
      '.'
    setNotice({ text, details: r.skipped.map((s) => `${s.reason}`) })
    clearSelection()
    await refresh()
  }

  async function handleUndo(bill) {
    const done = await run(() => undoBillTotal(bill.id))
    if (done) await refresh()
  }

  async function handleRevertToTotal(bill, category) {
    const ok = await dialogs.confirm({
      title: 'Turn back into a single total?',
      message:
        `${bill.shop} · ${bill.date}. Its ${bill.item_count || ''} item${bill.item_count === 1 ? '' : 's'} are replaced by one line ` +
        `for the full bill amount (${money(bill.amount, bill.currency)}). You can itemise it again any time.`,
      confirmLabel: 'Revert to total',
      danger: true,
    })
    if (!ok) return
    const done = await run(() => revertBillToTotal(bill.id, category))
    if (done) {
      setNotice({ text: `${bill.shop} is a single total of ${money(bill.amount, bill.currency)} again. Itemise it whenever you like.` })
      await refresh()
    }
  }

  // Itemise a pending / total-only bill, or edit the items of an itemised one: the Expenses page
  // works out which from the bill's status.
  function handleItemise(bill) {
    navigate('/expenses', { state: { itemiseBill: billForItemising(bill) } })
  }

  async function handleDismissDuplicate(id) {
    const done = await run(() => dismissDuplicate(id))
    if (done) await loadBills(queryRef.current)
  }

  // ── deleting ──
  async function handleDelete(bill) {
    const ok = await dialogs.confirm({
      title: 'Delete this bill?',
      message:
        `${bill.shop} · ${bill.date}` +
        (bill.status === 'itemised' ? '. The expenses made from it are kept.' : '. Its receipt is removed too.'),
      confirmLabel: 'Delete bill',
      danger: true,
    })
    if (!ok) return
    const done = await run(() => deletePendingBill(bill.id).then(() => true))
    if (done) await refresh()
  }

  async function handleBulkDelete() {
    const ids = [...selected]
    const ok = await dialogs.confirm({
      title: `Delete ${ids.length} bill${ids.length === 1 ? '' : 's'}?`,
      message: 'Bills with a recorded total are skipped: undo their total first. Receipts are removed with their bills.',
      confirmLabel: `Delete ${ids.length}`,
      danger: true,
    })
    if (!ok) return
    const r = await run(() => bulkDeleteBills(ids))
    if (!r) return
    setNotice({
      text: `Deleted ${r.deleted} bill${r.deleted === 1 ? '' : 's'}` + (r.skipped.length > 0 ? `, skipped ${r.skipped.length} (undo their recorded total first)` : '') + '.',
    })
    clearSelection()
    await refresh()
  }

  // ── receipts ──
  async function handleUploadReceipt(id, file) {
    const done = await run(() => uploadReceipt(id, file))
    if (done) await loadBills(queryRef.current)
  }

  function handleViewReceipt(id) {
    viewReceipt(id).catch((err) => setError(err.message))
  }

  async function handleDeleteReceipt(id) {
    const ok = await dialogs.confirm({
      title: 'Remove the receipt?',
      message: 'The bill stays; only the attached file is removed.',
      confirmLabel: 'Remove receipt',
      danger: true,
    })
    if (!ok) return
    const done = await run(() => deleteReceipt(id).then(() => true))
    if (done) await loadBills(queryRef.current)
  }

  async function handleToggleCount(enabled) {
    const updated = await run(() => saveCountBillsAsSpending(enabled))
    if (updated) setOptions(updated)
  }

  return {
    data,
    query,
    setQuery,
    loading,
    selected,
    toggleSelect,
    selectPage,
    clearSelection,
    notice,
    setNotice,
    dialog: dialogs.dialog,
    closeDialog: dialogs.close,
    form,
    setForm,
    actions: {
      add: handleAdd,
      uploadBill: handleUploadBill,
      bulkUpload: handleBulkUpload,
      recordTotal: handleRecordTotal,
      bulkRecord: handleBulkRecord,
      undo: handleUndo,
      revertToTotal: handleRevertToTotal,
      itemise: handleItemise,
      dismissDuplicate: handleDismissDuplicate,
      remove: handleDelete,
      bulkDelete: handleBulkDelete,
      uploadReceipt: handleUploadReceipt,
      viewReceipt: handleViewReceipt,
      deleteReceipt: handleDeleteReceipt,
      toggleCount: handleToggleCount,
    },
  }
}

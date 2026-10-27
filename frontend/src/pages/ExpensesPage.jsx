import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { money } from '../format.js'
import { EMPTY_DATE_FILTER, datesFor } from '../datePeriod.js'
import { suggestCategory, autoCategorize, fetchExpenses, fetchBill, fetchBillItems } from '../api/client.js'
import AddExpensePanel from '../components/expenses/AddExpensePanel.jsx'
import BulkEditPanel from '../components/expenses/BulkEditPanel.jsx'
import ExpenseFilters from '../components/expenses/ExpenseFilters.jsx'
import ExpensePager from '../components/expenses/ExpensePager.jsx'
import ExpenseTable from '../components/expenses/ExpenseTable.jsx'
import OptionLists from '../components/expenses/OptionLists.jsx'
import { EMPTY_BULK, KEEP } from '../components/expenses/shared.jsx'

export default function ExpensesPage({
  form,
  setForm,
  saving,
  onAdd,
  onAddBill,
  editingId,
  editForm,
  setEditForm,
  startEdit,
  cancelEdit,
  saveEdit,
  onDelete,
  onBulkUpdate,
  onBulkCopy,
  options,
  trips,
  groups,
  onError,
  embedded = false, // inside the Spending page, which supplies the title
  initialBillMode = false,
}) {
  // What an empty currency choice resolves to on the server: the chosen space's currency, else base.
  const defaultCurrency =
    groups.find((g) => String(g.id) === String(form.group_id))?.currency || options.base_currency || 'SEK'
  const effectiveCurrency = form.currency || defaultCurrency
  const [billMode, setBillMode] = useState(initialBillMode)
  const [billItems, setBillItems] = useState([])
  const [submittingBill, setSubmittingBill] = useState(false)
  const [receiptTotal, setReceiptTotal] = useState('')
  const [categorySuggestion, setCategorySuggestion] = useState(null)
  const [autoCatBusy, setAutoCatBusy] = useState(false)
  const [autoCatResult, setAutoCatResult] = useState(null)

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterShop, setFilterShop] = useState('')
  const [filterGroup, setFilterGroup] = useState('')
  const [dateFilter, setDateFilter] = useState(EMPTY_DATE_FILTER)
  const { date_from: dateFrom, date_to: dateTo } = datesFor(dateFilter)
  // "Edit together": tick expenses (or everything matching the filter) and change them in one go.
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [allMatching, setAllMatching] = useState(false)
  const [bulk, setBulk] = useState(EMPTY_BULK)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkNotice, setBulkNotice] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  // Under Spending the "By receipt" view already lists bills, so this view starts as a flat list of items.
  const [groupByBill, setGroupByBill] = useState(!embedded)
  const [filterTotalOnly, setFilterTotalOnly] = useState(false)
  // The bill whose items are being entered (set when coming from the Bills page or a total-only row).
  const [itemisingBill, setItemisingBill] = useState(null)
  const location = useLocation()
  const navigate = useNavigate()
  const [expandedBillKeys, setExpandedBillKeys] = useState(() => new Set())

  const [pageExpenses, setPageExpenses] = useState([])
  const [total, setTotal] = useState(0)
  const [loadingExpenses, setLoadingExpenses] = useState(true)

  function toggleBillGroup(key) {
    setExpandedBillKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const groupName = (id) => (groups || []).concat(trips || []).find((g) => g.id === id)?.name
  const groupSpaceType = (id) => (groups || []).concat(trips || []).find((g) => g.id === id)?.space_type || 'trip'
  const allSpaces = (groups || []).concat(trips || [])
  const canEditExpense = (e) => !e.group_id || allSpaces.find((g) => g.id === e.group_id)?.role !== 'viewer'

  // Debounce free-text search so it doesn't fire a request per keystroke.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedSearch(search.trim()), 400)
    return () => clearTimeout(handle)
  }, [search])

  const refetch = useCallback(() => {
    setLoadingExpenses(true)
    return fetchExpenses({
      scope: filterGroup,
      search: debouncedSearch,
      category: filterCategory,
      shop: filterShop,
      date_from: dateFrom,
      date_to: dateTo,
      total_only: filterTotalOnly ? 'true' : '',
      page,
      page_size: pageSize,
    })
      .then((res) => {
        setPageExpenses(res.items)
        setTotal(res.total)
      })
      .catch((err) => onError?.(err.message))
      .finally(() => setLoadingExpenses(false))
  }, [filterGroup, debouncedSearch, filterCategory, filterShop, dateFrom, dateTo, filterTotalOnly, page, pageSize, onError])

  // Fetch the current page whenever filters/pagination change (and once on mount).
  useEffect(() => {
    refetch()
  }, [refetch])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const currentPage = Math.min(page, totalPages)
  const pageStart = total === 0 ? 0 : (currentPage - 1) * pageSize

  // Once a mutation (add/edit/import/…) completes elsewhere, re-pull this page.
  async function afterMutation(promise) {
    const result = await promise
    await refetch()
    return result
  }

  // Same, but for deletes: clamps back a page if that was the last item on it
  // (the effect below then refetches for the new page automatically).
  async function afterDelete(promise) {
    const result = await promise
    if (page > 1 && pageExpenses.length === 1) {
      setPage((p) => Math.max(1, p - 1))
    } else {
      await refetch()
    }
    return result
  }

  // Club same-day, same-shop rows into one "bill" group (mirrors how a single
  // receipt is entered, whether one at a time or via bill mode). Rows without a
  // shop aren't grouped — there's nothing tying them to the same receipt.
  const billGroups = useMemo(() => {
    const groups = []
    const indexByKey = new Map()
    for (const e of pageExpenses) {
      const shop = (e.shop || '').trim()
      const key = shop
        ? `${e.date}::${shop}::${e.group_id ?? 'personal'}::${e.currency || 'SEK'}`
        : `single-${e.id}`
      let group = indexByKey.get(key)
      if (!group) {
        group = { key, date: e.date, shop, group_id: e.group_id, currency: e.currency || 'SEK', items: [] }
        indexByKey.set(key, group)
        groups.push(group)
      }
      group.items.push(e)
    }
    return groups
  }, [pageExpenses])

  function resetToFirstPage(setter) {
    return (value) => {
      setter(value)
      setPage(1)
    }
  }

  const hasActiveFilters = search || filterCategory || filterShop || filterGroup || dateFrom || dateTo || filterTotalOnly

  function clearFilters() {
    setSearch('')
    setFilterCategory('')
    setFilterShop('')
    setFilterGroup('')
    setDateFilter(EMPTY_DATE_FILTER)
    setFilterTotalOnly(false)
    setPage(1)
  }

  // ── Edit together ────────────────────────────────────────────────────────
  // A different set of results starts the selection over: it was chosen from other rows.
  useEffect(() => {
    setSelectedIds(new Set())
    setAllMatching(false)
  }, [filterGroup, debouncedSearch, filterCategory, filterShop, dateFrom, dateTo, filterTotalOnly])

  const editableIds = pageExpenses.filter(canEditExpense).map((e) => e.id)
  const isSelected = (id) => allMatching || selectedIds.has(id)
  const selectionState = (ids) => (ids.length && ids.every(isSelected) ? 'all' : ids.some(isSelected) ? 'some' : 'none')
  const selectedCount = allMatching ? total : selectedIds.size
  const pageAllSelected = editableIds.length > 0 && editableIds.every(isSelected)
  const COLS = selectMode ? 11 : 10

  // Ticking or unticking while "all matching" is on narrows it to this page's rows first.
  function setSelected(ids, on) {
    setSelectedIds((prev) => {
      const next = new Set(allMatching ? editableIds : prev)
      for (const id of ids) {
        if (on) next.add(id)
        else next.delete(id)
      }
      return next
    })
    setAllMatching(false)
  }

  function clearSelection() {
    setSelectedIds(new Set())
    setAllMatching(false)
  }

  function toggleSelectMode() {
    setSelectMode((on) => !on)
    clearSelection()
    setBulk(EMPTY_BULK)
    setBulkNotice('')
  }

  // Only the fields that were filled in are changed; a blank one means "leave as it is".
  const bulkChanges = {}
  for (const key of ['category', 'subcategory', 'shop', 'description']) {
    if (bulk[key].trim()) bulkChanges[key] = bulk[key].trim()
  }
  if (bulk.group_id !== KEEP) bulkChanges.group_id = bulk.group_id === '' ? null : parseInt(bulk.group_id, 10)
  const hasBulkChanges = Object.keys(bulkChanges).length > 0

  function describeBulkChanges() {
    const parts = []
    if (bulkChanges.category) parts.push(`Category → ${bulkChanges.category}`)
    if (bulkChanges.subcategory) parts.push(`Subcategory → ${bulkChanges.subcategory}`)
    if (bulkChanges.shop) parts.push(`Shop → ${bulkChanges.shop}`)
    if (bulkChanges.description) parts.push(`Item name → ${bulkChanges.description}`)
    if ('group_id' in bulkChanges) parts.push(`Space → ${bulkChanges.group_id === null ? 'Personal' : groupName(bulkChanges.group_id) || 'that space'}`)
    return parts.join(' · ')
  }

  async function applyBulk() {
    const body = allMatching
      ? {
          filters: {
            scope: filterGroup || undefined,
            search: debouncedSearch || undefined,
            category: filterCategory || undefined,
            shop: filterShop || undefined,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            total_only: filterTotalOnly ? true : undefined,
          },
          changes: bulkChanges,
        }
      : { ids: [...selectedIds], changes: bulkChanges }
    setBulkBusy(true)
    setBulkNotice('')
    try {
      const res = await onBulkUpdate(body)
      await refetch()
      setBulkNotice(`Updated ${res.updated} expense${res.updated === 1 ? '' : 's'}.`)
      clearSelection()
      setBulk(EMPTY_BULK)
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBulkBusy(false)
    }
  }

  // Copy the selection into a space (a trip, say). The originals stay where they are.
  const [copyTarget, setCopyTarget] = useState('')

  async function applyCopy() {
    const group_id = parseInt(copyTarget, 10)
    if (!Number.isInteger(group_id)) return
    const body = allMatching
      ? {
          filters: {
            scope: filterGroup || undefined,
            search: debouncedSearch || undefined,
            category: filterCategory || undefined,
            shop: filterShop || undefined,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            total_only: filterTotalOnly ? true : undefined,
          },
          group_id,
        }
      : { ids: [...selectedIds], group_id }
    setBulkBusy(true)
    setBulkNotice('')
    try {
      const res = await onBulkCopy(body)
      await refetch()
      const where = groupName(group_id) || 'that space'
      const skipped = res.skipped ? ` ${res.skipped} already there, skipped.` : ''
      setBulkNotice(`Copied ${res.copied} expense${res.copied === 1 ? '' : 's'} to ${where}.${skipped}`)
      clearSelection()
      setCopyTarget('')
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBulkBusy(false)
    }
  }

  // Suggest a category from the user's own shop history (or keyword rules) while
  // they're filling in the add-expense form, but only if they haven't chosen one yet.
  useEffect(() => {
    if (form.category.trim() || (!form.shop.trim() && !form.description.trim())) {
      setCategorySuggestion(null)
      return
    }
    const handle = setTimeout(() => {
      suggestCategory(form.description, form.shop)
        .then((res) => setCategorySuggestion(res.category ? res : null))
        .catch(() => setCategorySuggestion(null))
    }, 400)
    return () => clearTimeout(handle)
  }, [form.shop, form.description, form.category])

  function applySuggestion() {
    if (!categorySuggestion) return
    setForm((f) => ({
      ...f,
      category: categorySuggestion.category,
      subcategory: categorySuggestion.subcategory || f.subcategory,
    }))
    setCategorySuggestion(null)
  }

  async function handleAutoCategorize() {
    setAutoCatBusy(true)
    setAutoCatResult(null)
    try {
      const res = await autoCategorize()
      setAutoCatResult(`Categorized ${res.updated} expense(s).`)
      await refetch()
    } catch (err) {
      setAutoCatResult(err.message)
    } finally {
      setAutoCatBusy(false)
    }
  }

  const billTotal = billItems.reduce((sum, it) => sum + it.amount, 0)
  const receiptTotalNum = receiptTotal.trim() === '' ? null : parseFloat(receiptTotal)
  const billMismatch =
    receiptTotalNum !== null && !Number.isNaN(receiptTotalNum) ? Math.round((billTotal - receiptTotalNum) * 100) / 100 : null

  function toggleBillMode() {
    if (billMode && billItems.length > 0 && !window.confirm(`Discard ${billItems.length} unsaved item(s) from this bill?`)) {
      return
    }
    if (billMode && itemisingBill) setForm((f) => ({ ...f, shop: '' }))
    setBillMode((v) => !v)
    setBillItems([])
    setReceiptTotal('')
    setItemisingBill(null)
  }

  // Re-itemising: open bill mode with the bill's current items loaded, ready to change, remove or add to.
  // Saving replaces those items.
  async function beginReitemising(bill) {
    let existing
    try {
      existing = await fetchBillItems(bill.id)
    } catch (err) {
      onError?.(err.message)
      return
    }
    const first = existing[0]
    setItemisingBill({ ...bill, reitemise: true })
    setBillMode(true)
    setBillItems(
      existing.map((e) => ({
        category: e.category,
        subcategory: e.subcategory || '',
        description: e.description || '',
        brand: e.brand || '',
        amount: Number(e.amount),
        currency: e.currency,
        quantity: Number(e.quantity) || 1,
        unit: e.unit || 'Count',
      })),
    )
    setReceiptTotal(String(Number(bill.amount)))
    setForm((f) => ({
      ...f,
      date: first?.date || bill.date,
      shop: first ? first.shop || '' : bill.shop,
      currency: first?.currency || bill.currency,
      group_id: first?.group_id ? String(first.group_id) : '',
      category: '',
      subcategory: '',
      description: '',
      brand: '',
      amount: '',
      quantity: '1',
      unit: 'Count',
    }))
    document.getElementById('add-expense-panel')?.scrollIntoView?.({ behavior: 'smooth' })
  }

  // Start entering the items of a bill: bill mode, with its date/shop/currency/total filled in.
  // An already-itemised bill is re-itemised instead (its current items are loaded).
  function beginItemising(bill) {
    if (bill.status === 'itemised') return beginReitemising(bill)
    setItemisingBill(bill)
    setBillMode(true)
    setBillItems([])
    setReceiptTotal(String(Number(bill.amount)))
    setForm((f) => ({
      ...f,
      date: bill.date,
      shop: bill.shop,
      currency: bill.currency,
      group_id: '',
      category: '',
      subcategory: '',
      description: '',
      brand: '',
      amount: '',
      quantity: '1',
      unit: 'Count',
    }))
    document.getElementById('add-expense-panel')?.scrollIntoView?.({ behavior: 'smooth' })
  }

  // Arriving from the Bills page ("Itemise"): pick the bill up from the navigation state, then clear it
  // so a refresh doesn't start itemising again.
  useEffect(() => {
    const bill = location.state?.itemiseBill
    if (!bill) return
    beginItemising(bill)
    navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state])

  // From a total-only row: the expense stands in for its bill (same date, shop name, amount, currency).
  function itemiseFromExpense(e) {
    beginItemising({
      id: e.source_bill_id,
      date: e.date,
      shop: e.description,
      amount: e.amount,
      currency: e.currency,
      status: 'total_only',
    })
  }

  // In bill mode, submitting the form stashes the current line item locally
  // instead of saving it, so the item fields can be reused for the next one.
  async function handleFormSubmit(e) {
    if (!billMode) {
      await afterMutation(onAdd(e))
      return
    }
    e.preventDefault()
    setBillItems((prev) => [
      ...prev,
      {
        category: form.category,
        subcategory: form.subcategory,
        description: form.description,
        brand: form.brand,
        amount: parseFloat(form.amount),
        currency: effectiveCurrency,
        quantity: parseFloat(form.quantity) || 1,
        unit: form.unit || 'Count',
      },
    ])
    setForm((f) => ({ ...f, category: '', subcategory: '', description: '', brand: '', amount: '', quantity: '1', unit: 'Count' }))
  }

  function removeBillItem(i) {
    setBillItems((prev) => prev.filter((_, idx) => idx !== i))
  }

  // Move a line back into the form to change it, then add it again.
  function editBillItem(i) {
    const it = billItems[i]
    if (!it) return
    setForm((f) => ({
      ...f,
      category: it.category,
      subcategory: it.subcategory || '',
      description: it.description || '',
      brand: it.brand || '',
      amount: String(it.amount),
      quantity: String(it.quantity),
      unit: it.unit || 'Count',
      currency: it.currency,
    }))
    removeBillItem(i)
  }

  // From the header of an itemised bill: load the bill and open its items for editing.
  async function editItemsOfBill(billId) {
    try {
      beginItemising(await fetchBill(billId))
    } catch (err) {
      onError?.(err.message)
    }
  }

  async function handleSubmitBill() {
    if (billItems.length === 0) return
    if (billMismatch !== null && billMismatch !== 0) {
      const direction = billMismatch > 0 ? 'more than' : 'less than'
      if (
        !window.confirm(
          `Your items add up to ${money(billTotal, effectiveCurrency)}, ${direction} the receipt total of ${money(receiptTotalNum, effectiveCurrency)} ` +
            `(off by ${money(Math.abs(billMismatch), effectiveCurrency)}). Submit anyway?`,
        )
      ) {
        return
      }
    }
    setSubmittingBill(true)
    try {
      await afterMutation(
        onAddBill(
          billItems.map((it) => ({
            date: form.date,
            category: it.category,
            subcategory: it.subcategory,
            description: it.description,
            amount: it.amount,
            quantity: it.quantity,
            unit: it.unit,
            shop: form.shop,
            brand: it.brand,
            currency: it.currency || effectiveCurrency,
            group_id: form.group_id ? parseInt(form.group_id, 10) : null,
          })),
          itemisingBill?.id,
          // Adding a new bill: have its bill record made. Itemising an existing one links to that bill.
          itemisingBill ? (itemisingBill.reitemise ? { replace: true } : undefined) : { asBill: true },
        ),
      )
      setBillItems([])
      setReceiptTotal('')
      if (itemisingBill) {
        setItemisingBill(null)
        setBillMode(false)
      }
      setForm((f) => ({
        ...f,
        category: '',
        subcategory: '',
        description: '',
        brand: '',
        amount: '',
        quantity: '1',
        unit: 'Count',
        shop: '',
      }))
    } finally {
      setSubmittingBill(false)
    }
  }

  const rowProps = {
      editingId,
      editForm,
      setEditForm,
      startEdit,
      cancelEdit,
      saveEdit,
      onDelete,
      options,
      selectMode,
      groupName,
      groupSpaceType,
      allSpaces,
      canEditExpense,
      isSelected,
      COLS,
      setSelected,
      itemiseFromExpense,
      afterMutation,
      afterDelete,
    }


  return (
    <>
      {!embedded && <h1 className="page-title">🧾 Expenses</h1>}

      <AddExpensePanel
        form={form}
        setForm={setForm}
        saving={saving}
        options={options}
        onError={onError}
        defaultCurrency={defaultCurrency}
        effectiveCurrency={effectiveCurrency}
        billMode={billMode}
        billItems={billItems}
        submittingBill={submittingBill}
        receiptTotal={receiptTotal}
        setReceiptTotal={setReceiptTotal}
        categorySuggestion={categorySuggestion}
        autoCatBusy={autoCatBusy}
        autoCatResult={autoCatResult}
        itemisingBill={itemisingBill}
        allSpaces={allSpaces}
        applySuggestion={applySuggestion}
        handleAutoCategorize={handleAutoCategorize}
        billTotal={billTotal}
        receiptTotalNum={receiptTotalNum}
        billMismatch={billMismatch}
        toggleBillMode={toggleBillMode}
        handleFormSubmit={handleFormSubmit}
        removeBillItem={removeBillItem}
        editBillItem={editBillItem}
        handleSubmitBill={handleSubmitBill}
      />
      <OptionLists form={form} editForm={editForm} options={options} bulk={bulk} />

      {(total > 0 || hasActiveFilters) && (
        <ExpenseFilters
          options={options}
          search={search}
          filterCategory={filterCategory}
          filterShop={filterShop}
          filterGroup={filterGroup}
          dateFilter={dateFilter}
          setDateFilter={setDateFilter}
          selectMode={selectMode}
          groupByBill={groupByBill}
          setGroupByBill={setGroupByBill}
          filterTotalOnly={filterTotalOnly}
          allSpaces={allSpaces}
          hasActiveFilters={hasActiveFilters}
          clearFilters={clearFilters}
          resetToFirstPage={resetToFirstPage}
          setSearch={setSearch}
          setFilterCategory={setFilterCategory}
          setFilterShop={setFilterShop}
          setFilterGroup={setFilterGroup}
          setFilterTotalOnly={setFilterTotalOnly}
          toggleSelectMode={toggleSelectMode}
        />
      )}

      {selectMode && (
      <BulkEditPanel
        pageExpenses={pageExpenses}
        allMatching={allMatching}
        setAllMatching={setAllMatching}
        bulk={bulk}
        setBulk={setBulk}
        bulkBusy={bulkBusy}
        bulkNotice={bulkNotice}
        total={total}
        allSpaces={allSpaces}
        selectedCount={selectedCount}
        pageAllSelected={pageAllSelected}
        clearSelection={clearSelection}
        hasBulkChanges={hasBulkChanges}
        describeBulkChanges={describeBulkChanges}
        applyBulk={applyBulk}
        copyTarget={copyTarget}
        setCopyTarget={setCopyTarget}
        applyCopy={applyCopy}
      />
      )}

      {loadingExpenses && <p className="subtitle">Loading…</p>}

      {!loadingExpenses && total > 0 && (
        <ExpenseTable
          rowProps={rowProps}
          selectMode={selectMode}
          groupByBill={groupByBill}
          expandedBillKeys={expandedBillKeys}
          pageExpenses={pageExpenses}
          toggleBillGroup={toggleBillGroup}
          canEditExpense={canEditExpense}
          editableIds={editableIds}
          selectionState={selectionState}
          COLS={COLS}
          setSelected={setSelected}
          itemiseFromExpense={itemiseFromExpense}
          editItemsOfBill={editItemsOfBill}
          billGroups={billGroups}
        />
      )}

      {total > 0 && (
          <ExpensePager
            setPage={setPage}
            pageSize={pageSize}
            setPageSize={setPageSize}
            total={total}
            totalPages={totalPages}
            currentPage={currentPage}
            pageStart={pageStart}
          />
      )}

      {!loadingExpenses && total === 0 && (
        <p className="subtitle">{hasActiveFilters ? 'No expenses match your filters.' : 'No expenses yet — add one above.'}</p>
      )}
    </>
  )
}

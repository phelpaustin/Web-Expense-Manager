import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { money } from '../format.js'
import { suggestCategory, autoCategorize, fetchExpenses } from '../api/client.js'

const PAGE_SIZES = [10, 25, 50, 100]

const SPACE_TYPE_ICONS = { household: '🏠', business: '💼', rental: '🏢', trip: '✈️', custom: '📁' }

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
  options,
  onImport,
  onExport,
  importCurrency,
  setImportCurrency,
  onAddRow,
  trips,
  groups,
  onError,
}) {
  const [billMode, setBillMode] = useState(false)
  const [billItems, setBillItems] = useState([])
  const [submittingBill, setSubmittingBill] = useState(false)
  const [receiptTotal, setReceiptTotal] = useState('')
  const [file, setFile] = useState(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [skipped, setSkipped] = useState([])
  const [categorySuggestion, setCategorySuggestion] = useState(null)
  const [autoCatBusy, setAutoCatBusy] = useState(false)
  const [autoCatResult, setAutoCatResult] = useState(null)

  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterShop, setFilterShop] = useState('')
  const [filterGroup, setFilterGroup] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [groupByBill, setGroupByBill] = useState(true)
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
      page,
      page_size: pageSize,
    })
      .then((res) => {
        setPageExpenses(res.items)
        setTotal(res.total)
      })
      .catch((err) => onError?.(err.message))
      .finally(() => setLoadingExpenses(false))
  }, [filterGroup, debouncedSearch, filterCategory, filterShop, dateFrom, dateTo, page, pageSize, onError])

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

  const hasActiveFilters = search || filterCategory || filterShop || filterGroup || dateFrom || dateTo

  function clearFilters() {
    setSearch('')
    setFilterCategory('')
    setFilterShop('')
    setFilterGroup('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
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
    setBillMode((v) => !v)
    setBillItems([])
    setReceiptTotal('')
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
        currency: form.currency || 'SEK',
        quantity: parseFloat(form.quantity) || 1,
        unit: form.unit || 'Count',
      },
    ])
    setForm((f) => ({ ...f, category: '', subcategory: '', description: '', brand: '', amount: '', quantity: '1', unit: 'Count' }))
  }

  function removeBillItem(i) {
    setBillItems((prev) => prev.filter((_, idx) => idx !== i))
  }

  async function handleSubmitBill() {
    if (billItems.length === 0) return
    if (billMismatch !== null && billMismatch !== 0) {
      const direction = billMismatch > 0 ? 'more than' : 'less than'
      if (
        !window.confirm(
          `Your items add up to ${money(billTotal, form.currency)}, ${direction} the receipt total of ${money(receiptTotalNum, form.currency)} ` +
            `(off by ${money(Math.abs(billMismatch), form.currency)}). Submit anyway?`,
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
            currency: it.currency || form.currency || 'SEK',
            group_id: form.group_id ? parseInt(form.group_id, 10) : null,
          })),
        ),
      )
      setBillItems([])
      setReceiptTotal('')
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

  async function handleImportSubmit(e) {
    e.preventDefault()
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const result = await afterMutation(onImport(file))
      setImportResult(result)
      setSkipped(result.skipped_rows || [])
      setFile(null)
      e.target.reset()
    } catch (err) {
      setImportResult({ error: err.message })
    } finally {
      setImporting(false)
    }
  }

  function updateSkipped(i, field, value) {
    setSkipped((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)))
  }

  async function addSkipped(i) {
    const r = skipped[i]
    try {
      await afterMutation(
        onAddRow({
          date: r.date,
          category: r.category,
          subcategory: r.subcategory,
          description: r.description,
          amount: parseFloat(r.amount),
          quantity: parseFloat(r.quantity) || 1,
          unit: r.unit || 'Count',
          shop: r.shop,
          brand: r.brand,
          currency: r.currency || 'SEK',
        }),
      )
      setSkipped((prev) => prev.filter((_, idx) => idx !== i))
    } catch (err) {
      updateSkipped(i, 'reason', err.message)
    }
  }

  function renderExpenseRow(e) {
    if (editingId === e.id) {
      return (
        <tr key={e.id} className="editing">
          <td>
            <input
              type="date"
              value={editForm.date}
              onChange={(ev) => setEditForm({ ...editForm, date: ev.target.value })}
            />
          </td>
          <td>
            <input
              type="text"
              list="cat-options"
              value={editForm.category}
              onChange={(ev) => setEditForm({ ...editForm, category: ev.target.value })}
            />
          </td>
          <td>
            <input
              type="text"
              list="subcat-edit-options"
              value={editForm.subcategory}
              onChange={(ev) => setEditForm({ ...editForm, subcategory: ev.target.value })}
            />
          </td>
          <td>
            <input
              type="text"
              list="shop-options"
              value={editForm.shop}
              onChange={(ev) => setEditForm({ ...editForm, shop: ev.target.value })}
            />
          </td>
          <td>
            <input
              type="text"
              value={editForm.description}
              onChange={(ev) => setEditForm({ ...editForm, description: ev.target.value })}
            />
          </td>
          <td>
            {allSpaces.length > 0 ? (
              <select
                value={editForm.group_id || ''}
                onChange={(ev) => setEditForm({ ...editForm, group_id: ev.target.value })}
                title="Move this expense to a different Expense Space (or personal)"
              >
                <option value="">Personal expenses</option>
                {allSpaces
                  .filter((g) => g.role !== 'viewer')
                  .map((g) => (
                    <option key={g.id} value={g.id}>
                      {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
                    </option>
                  ))}
              </select>
            ) : (
              '—'
            )}
          </td>
          <td className="right">
            <input
              type="number"
              step="0.01"
              min="0.01"
              className="amount-input"
              value={editForm.quantity}
              onChange={(ev) => setEditForm({ ...editForm, quantity: ev.target.value })}
            />
          </td>
          <td>
            <input
              type="text"
              list="unit-options"
              className="unit-input"
              value={editForm.unit}
              onChange={(ev) => setEditForm({ ...editForm, unit: ev.target.value })}
            />
          </td>
          <td className="right">
            <input
              type="number"
              step="0.01"
              min="0.01"
              className="amount-input"
              value={editForm.amount}
              onChange={(ev) => setEditForm({ ...editForm, amount: ev.target.value })}
            />
          </td>
          <td className="right nowrap">
            <button className="icon-btn save" onClick={() => afterMutation(saveEdit(e.id))} title="Save">
              ✓
            </button>
            <button className="icon-btn" onClick={cancelEdit} title="Cancel">
              ✕
            </button>
          </td>
        </tr>
      )
    }
    return (
      <tr key={e.id}>
        <td>{e.date}</td>
        <td>{e.category}</td>
        <td>{e.subcategory}</td>
        <td>{e.shop}</td>
        <td>{e.description}</td>
        <td>
          {groupName(e.group_id) ? (
            <span title={e.created_by ? `Added by ${e.created_by}` : undefined}>
              {SPACE_TYPE_ICONS[groupSpaceType(e.group_id)] || '📁'} {groupName(e.group_id)}
            </span>
          ) : (
            '—'
          )}
        </td>
        <td className="right">{e.quantity}</td>
        <td>{e.unit}</td>
        <td className="right" title={`${e.price_per_unit}/unit · ${e.currency}`}>
          {money(e.amount, e.currency)}
        </td>
        <td className="right nowrap">
          {canEditExpense(e) && (
            <>
              <button className="icon-btn" onClick={() => startEdit(e)} title="Edit">
                ✎
              </button>
              <button className="delete-btn" onClick={() => afterDelete(onDelete(e.id))} title="Delete">
                ✕
              </button>
            </>
          )}
        </td>
      </tr>
    )
  }

  return (
    <>
      <h1 className="page-title">🧾 Expenses</h1>

      <section className="panel">
        <h2>📤 Import / Export</h2>
        <p className="subtitle">
          Import a CSV or Excel file (old dashboard format supported). Duplicates are skipped.
        </p>
        <form className="add-form" onSubmit={handleImportSubmit}>
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
          <select
            value={importCurrency}
            onChange={(e) => setImportCurrency(e.target.value)}
            title="Currency for imported rows"
          >
            <option value="">Currency: from file</option>
            <option value="SEK">SEK</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
            <option value="INR">INR</option>
          </select>
          <button type="submit" disabled={!file || importing}>
            {importing ? 'Importing…' : 'Import'}
          </button>
          <button type="button" className="ghost-btn" onClick={() => onExport('csv')}>
            Export CSV
          </button>
          <button type="button" className="ghost-btn" onClick={() => onExport('xlsx')}>
            Export Excel
          </button>
        </form>
        {importResult && (
          <div className={importResult.error ? 'auth-error' : 'ok-note'} style={{ marginTop: '0.75rem' }}>
            {importResult.error
              ? importResult.error
              : `Imported ${importResult.added} · skipped ${importResult.skipped}` +
                (importResult.errors && importResult.errors.length
                  ? ` · ${importResult.errors.length} row error(s)`
                  : '')}
          </div>
        )}
      </section>

      {skipped.length > 0 && (
        <section className="panel">
          <h2>⚠️ Skipped rows ({skipped.length})</h2>
          <p className="subtitle">Fix any values and add them back individually.</p>
          <table className="table">
            <thead>
              <tr>
                <th>Reason</th>
                <th>Date</th>
                <th>Category</th>
                <th>Subcat</th>
                <th>Shop</th>
                <th>Description</th>
                <th className="right">Qty</th>
                <th>Unit</th>
                <th>Cur</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {skipped.map((r, i) => (
                <tr key={i}>
                  <td className="skip-reason">{r.reason}</td>
                  <td>
                    <input type="date" value={r.date} onChange={(e) => updateSkipped(i, 'date', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" list="cat-options" value={r.category} onChange={(e) => updateSkipped(i, 'category', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" value={r.subcategory} onChange={(e) => updateSkipped(i, 'subcategory', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" list="shop-options" value={r.shop} onChange={(e) => updateSkipped(i, 'shop', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" value={r.description} onChange={(e) => updateSkipped(i, 'description', e.target.value)} />
                  </td>
                  <td className="right">
                    <input type="number" className="amount-input" value={r.quantity} onChange={(e) => updateSkipped(i, 'quantity', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" list="unit-options" className="unit-input" value={r.unit} onChange={(e) => updateSkipped(i, 'unit', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" className="unit-input" value={r.currency} onChange={(e) => updateSkipped(i, 'currency', e.target.value)} />
                  </td>
                  <td className="right">
                    <input type="number" className="amount-input" value={r.amount} onChange={(e) => updateSkipped(i, 'amount', e.target.value)} />
                  </td>
                  <td className="right nowrap">
                    <button className="icon-btn save" onClick={() => addSkipped(i)} title="Add this row">
                      ✓
                    </button>
                    <button
                      className="delete-btn"
                      onClick={() => setSkipped((prev) => prev.filter((_, idx) => idx !== i))}
                      title="Dismiss"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel">
        <h2>➕ Add expense</h2>
        <div className="auto-cat-row">
          <button type="button" className="ghost-btn" onClick={toggleBillMode}>
            {billMode ? '✕ Exit bill mode' : '🧾 Add by bill'}
          </button>
          {billMode && (
            <span className="subtitle">
              Add every item from one receipt, then submit them all together. Date/shop/currency/space are shared by
              the whole bill.
            </span>
          )}
        </div>
        <form className="add-form" onSubmit={handleFormSubmit}>
          <input
            type="date"
            required
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
          <input
            type="text"
            list="cat-options"
            placeholder="Category"
            required
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          />
          {categorySuggestion && (
            <button type="button" className="suggestion-chip" onClick={applySuggestion}>
              💡 {categorySuggestion.category}?
            </button>
          )}
          <input
            type="text"
            list="subcat-add-options"
            placeholder="Subcategory"
            value={form.subcategory}
            onChange={(e) => setForm({ ...form, subcategory: e.target.value })}
          />
          <input
            type="text"
            list="shop-options"
            placeholder="Shop"
            value={form.shop}
            onChange={(e) => setForm({ ...form, shop: e.target.value })}
          />
          <input
            type="text"
            placeholder="Brand"
            value={form.brand}
            onChange={(e) => setForm({ ...form, brand: e.target.value })}
          />
          <input
            type="text"
            placeholder="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Qty"
            className="qty-input"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
          />
          <input
            type="text"
            list="unit-options"
            placeholder="Unit"
            className="unit-input"
            value={form.unit}
            onChange={(e) => setForm({ ...form, unit: e.target.value })}
          />
          <input
            type="text"
            placeholder="Cur"
            className="unit-input"
            value={form.currency}
            disabled={billMode && billItems.length > 0}
            onChange={(e) => setForm({ ...form, currency: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
          {allSpaces.length > 0 && (
            <select
              value={form.group_id || ''}
              onChange={(e) => setForm({ ...form, group_id: e.target.value })}
              title="Add this expense to an Expense Space or trip (optional)"
            >
              <option value="">Personal expenses</option>
              {allSpaces
                .filter((g) => g.role !== 'viewer')
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
                  </option>
                ))}
            </select>
          )}
          <button type="submit" disabled={billMode ? false : saving}>
            {billMode ? '➕ Add item to bill' : saving ? 'Saving…' : 'Add'}
          </button>
        </form>

        {billMode && (
          <div className="bill-tray">
            {billItems.length === 0 ? (
              <p className="subtitle">No items added yet — fill in the fields above and click "Add item to bill".</p>
            ) : (
              <>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th>Description</th>
                      <th className="right">Qty</th>
                      <th>Unit</th>
                      <th className="right">Amount</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {billItems.map((it, i) => (
                      <tr key={i}>
                        <td>{it.category}</td>
                        <td>{it.description}</td>
                        <td className="right">{it.quantity}</td>
                        <td>{it.unit}</td>
                        <td className="right">{money(it.amount, it.currency)}</td>
                        <td className="right nowrap">
                          <button className="delete-btn" onClick={() => removeBillItem(i)} title="Remove">
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="bill-total-row">
                  <strong>
                    Bill total so far: {money(billTotal, form.currency)} ({billItems.length} item{billItems.length === 1 ? '' : 's'})
                  </strong>
                  <label className="receipt-total-input">
                    Receipt total
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="e.g. from the printed total"
                      value={receiptTotal}
                      onChange={(e) => setReceiptTotal(e.target.value)}
                    />
                  </label>
                </div>
                {billMismatch !== null && (
                  <p className={billMismatch === 0 ? 'ok-note' : 'auth-error'}>
                    {billMismatch === 0
                      ? '✓ Matches the receipt total.'
                      : `⚠️ Items add up to ${money(billTotal, form.currency)}, ${billMismatch > 0 ? 'more than' : 'less than'} the receipt total ` +
                        `of ${money(receiptTotalNum, form.currency)} (off by ${money(Math.abs(billMismatch), form.currency)}).`}
                  </p>
                )}
                <button type="button" onClick={handleSubmitBill} disabled={submittingBill}>
                  {submittingBill ? 'Submitting…' : `✅ Submit bill (${money(billTotal, form.currency)})`}
                </button>
              </>
            )}
          </div>
        )}

        <div className="auto-cat-row">
          <button type="button" className="ghost-btn" onClick={handleAutoCategorize} disabled={autoCatBusy}>
            {autoCatBusy ? 'Categorizing…' : '🤖 Auto-categorize uncategorized expenses'}
          </button>
          {autoCatResult && <span className="subtitle">{autoCatResult}</span>}
        </div>

        {/* Shared option lists — type a new value to add it (auto-learned on save). */}
        <datalist id="cat-options">
          {options.categories.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
        <datalist id="subcat-add-options">
          {(options.subcategories[form.category] || []).map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
        <datalist id="subcat-edit-options">
          {(options.subcategories[editForm.category] || []).map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
        <datalist id="unit-options">
          {options.units.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>
        <datalist id="shop-options">
          {(options.shops || []).map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </section>

      {(total > 0 || hasActiveFilters) && (
        <section className="panel">
          <h2>🔍 Search &amp; filter</h2>
          <div className="add-form">
            <input
              type="text"
              placeholder="Search description, shop, brand…"
              value={search}
              onChange={(e) => resetToFirstPage(setSearch)(e.target.value)}
            />
            <select value={filterCategory} onChange={(e) => resetToFirstPage(setFilterCategory)(e.target.value)}>
              <option value="">All categories</option>
              {options.categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select value={filterShop} onChange={(e) => resetToFirstPage(setFilterShop)(e.target.value)}>
              <option value="">All shops</option>
              {(options.shops || []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            {allSpaces.length > 0 && (
              <select value={filterGroup} onChange={(e) => resetToFirstPage(setFilterGroup)(e.target.value)}>
                <option value="">All expenses</option>
                <option value="personal">Personal expenses</option>
                {allSpaces.map((g) => (
                  <option key={g.id} value={g.id}>
                    {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
                  </option>
                ))}
              </select>
            )}
            <input
              type="date"
              title="From date"
              value={dateFrom}
              onChange={(e) => resetToFirstPage(setDateFrom)(e.target.value)}
            />
            <input
              type="date"
              title="To date"
              value={dateTo}
              onChange={(e) => resetToFirstPage(setDateTo)(e.target.value)}
            />
            {hasActiveFilters && (
              <button type="button" className="ghost-btn" onClick={clearFilters}>
                Clear filters
              </button>
            )}
            <button type="button" className="ghost-btn" onClick={() => setGroupByBill((v) => !v)}>
              {groupByBill ? '📄 Flat view' : '🧾 Bill view'}
            </button>
          </div>
        </section>
      )}

      {loadingExpenses && <p className="subtitle">Loading…</p>}

      {!loadingExpenses && total > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Category</th>
              <th>Subcat</th>
              <th>Shop</th>
              <th>Description</th>
              <th>Group</th>
              <th className="right">Qty</th>
              <th>Unit</th>
              <th className="right">Amount</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {groupByBill
              ? billGroups.map((group) => {
                  const isExpanded = expandedBillKeys.has(group.key)
                  return (
                    <Fragment key={group.key}>
                      <tr className="bill-group-header clickable-row" onClick={() => toggleBillGroup(group.key)}>
                        <td colSpan={10}>
                          {isExpanded ? '▾' : '▸'} 🧾 {group.date} · {group.shop || 'No shop'} · {group.items.length}{' '}
                          item{group.items.length === 1 ? '' : 's'} · Bill total:{' '}
                          {money(group.items.reduce((sum, e) => sum + e.amount, 0), group.currency)}
                        </td>
                      </tr>
                      {isExpanded && group.items.map((e) => renderExpenseRow(e))}
                    </Fragment>
                  )
                })
              : pageExpenses.map((e) => renderExpenseRow(e))}
          </tbody>
        </table>
      )}

      {total > 0 && (
        <div className="pagination-bar">
          <span className="subtitle">
            Showing {pageStart + 1}–{Math.min(pageStart + pageSize, total)} of {total}
          </span>
          <div className="pagination-controls">
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} / page
                </option>
              ))}
            </select>
            <button type="button" className="ghost-btn" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>
              ← Prev
            </button>
            <span className="subtitle">
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              className="ghost-btn"
              disabled={currentPage >= totalPages}
              onClick={() => setPage(currentPage + 1)}
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {!loadingExpenses && total === 0 && (
        <p className="subtitle">{hasActiveFilters ? 'No expenses match your filters.' : 'No expenses yet — add one above.'}</p>
      )}
    </>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { money } from '../format.js'
import { suggestCategory, autoCategorize } from '../api/client.js'

const PAGE_SIZES = [10, 25, 50, 100]

const SPACE_TYPE_ICONS = { household: '🏠', business: '💼', rental: '🏢', trip: '✈️', custom: '📁' }

export default function ExpensesPage({
  expenses,
  form,
  setForm,
  saving,
  onAdd,
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
}) {
  const [file, setFile] = useState(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [skipped, setSkipped] = useState([])
  const [categorySuggestion, setCategorySuggestion] = useState(null)
  const [autoCatBusy, setAutoCatBusy] = useState(false)
  const [autoCatResult, setAutoCatResult] = useState(null)

  const [search, setSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterShop, setFilterShop] = useState('')
  const [filterGroup, setFilterGroup] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)

  const groupName = (id) => (groups || []).concat(trips || []).find((g) => g.id === id)?.name
  const groupSpaceType = (id) => (groups || []).concat(trips || []).find((g) => g.id === id)?.space_type || 'trip'
  const allSpaces = (groups || []).concat(trips || [])
  const canEditExpense = (e) => !e.group_id || allSpaces.find((g) => g.id === e.group_id)?.role !== 'viewer'

  const filteredExpenses = useMemo(() => {
    const q = search.trim().toLowerCase()
    return expenses
      .filter((e) => {
        if (filterCategory && e.category !== filterCategory) return false
        if (filterShop && e.shop !== filterShop) return false
        if (filterGroup === 'personal' && e.group_id) return false
        if (filterGroup && filterGroup !== 'personal' && String(e.group_id) !== filterGroup) return false
        if (dateFrom && e.date < dateFrom) return false
        if (dateTo && e.date > dateTo) return false
        if (q) {
          const haystack = `${e.description} ${e.shop} ${e.brand} ${e.category} ${e.subcategory}`.toLowerCase()
          if (!haystack.includes(q)) return false
        }
        return true
      })
      .slice()
      .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : b.id - a.id))
  }, [expenses, search, filterCategory, filterShop, filterGroup, dateFrom, dateTo])

  const totalPages = Math.max(1, Math.ceil(filteredExpenses.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const pageStart = (currentPage - 1) * pageSize
  const pagedExpenses = filteredExpenses.slice(pageStart, pageStart + pageSize)

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
    } catch (err) {
      setAutoCatResult(err.message)
    } finally {
      setAutoCatBusy(false)
    }
  }

  async function handleImportSubmit(e) {
    e.preventDefault()
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const result = await onImport(file)
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
      await onAddRow({
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
      })
      setSkipped((prev) => prev.filter((_, idx) => idx !== i))
    } catch (err) {
      updateSkipped(i, 'reason', err.message)
    }
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
            accept=".csv,.xlsx,.xls"
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
        <form className="add-form" onSubmit={onAdd}>
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
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Add'}
          </button>
        </form>

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

      {expenses.length > 0 && (
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
          </div>
        </section>
      )}

      {expenses.length > 0 && (
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
            {pagedExpenses.map((e) =>
              editingId === e.id ? (
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
                  <td>{groupName(e.group_id) || '—'}</td>
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
                    <button className="icon-btn save" onClick={() => saveEdit(e.id)} title="Save">
                      ✓
                    </button>
                    <button className="icon-btn" onClick={cancelEdit} title="Cancel">
                      ✕
                    </button>
                  </td>
                </tr>
              ) : (
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
                    {money(e.amount)}
                  </td>
                  <td className="right nowrap">
                    {canEditExpense(e) && (
                      <>
                        <button className="icon-btn" onClick={() => startEdit(e)} title="Edit">
                          ✎
                        </button>
                        <button className="delete-btn" onClick={() => onDelete(e.id)} title="Delete">
                          ✕
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      )}

      {filteredExpenses.length > 0 && (
        <div className="pagination-bar">
          <span className="subtitle">
            Showing {pageStart + 1}–{Math.min(pageStart + pageSize, filteredExpenses.length)} of{' '}
            {filteredExpenses.length}
            {hasActiveFilters ? ` (filtered from ${expenses.length})` : ''}
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

      {expenses.length > 0 && filteredExpenses.length === 0 && (
        <p className="subtitle">No expenses match your filters.</p>
      )}
    </>
  )
}

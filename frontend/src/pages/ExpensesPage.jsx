import { useState } from 'react'
import { money } from '../format.js'

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
}) {
  const [file, setFile] = useState(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)

  async function handleImportSubmit(e) {
    e.preventDefault()
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const result = await onImport(file)
      setImportResult(result)
      setFile(null)
      e.target.reset()
    } catch (err) {
      setImportResult({ error: err.message })
    } finally {
      setImporting(false)
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
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Add'}
          </button>
        </form>

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
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Category</th>
              <th>Subcat</th>
              <th>Shop</th>
              <th>Description</th>
              <th className="right">Qty</th>
              <th>Unit</th>
              <th className="right">Amount</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((e) =>
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
                  <td className="right">{e.quantity}</td>
                  <td>{e.unit}</td>
                  <td className="right" title={`${e.price_per_unit}/unit · ${e.currency}`}>
                    {money(e.amount)}
                  </td>
                  <td className="right nowrap">
                    <button className="icon-btn" onClick={() => startEdit(e)} title="Edit">
                      ✎
                    </button>
                    <button className="delete-btn" onClick={() => onDelete(e.id)} title="Delete">
                      ✕
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      )}
    </>
  )
}

import { useState } from 'react'
import { createExpense, importExpenses } from '../api/client.js'
import UnitSelect from './UnitSelect.jsx'

const FALLBACK_CURRENCIES = ['SEK', 'USD', 'EUR', 'GBP', 'INR']

// Loads a spreadsheet that is already in this app's expense format (what Export produces, or the old
// dashboard's): items with subcategory, quantity, unit and brand. Rows that could not be imported are
// listed so each can be fixed and added back by hand.
export default function ExpenseFileImport({ options, onImported, onError }) {
  const [file, setFile] = useState(null)
  const [currency, setCurrency] = useState('')
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const [skipped, setSkipped] = useState([])
  const currencies = (options && options.currencies && options.currencies.length ? options.currencies : FALLBACK_CURRENCIES)
  const units = (options && options.units) || []

  async function submit(e) {
    e.preventDefault()
    if (!file) return
    const form = e.target
    setImporting(true)
    setResult(null)
    try {
      const res = await importExpenses(file, currency)
      setResult(res)
      setSkipped(res.skipped_rows || [])
      setFile(null)
      form.reset()
      if (onImported) await onImported()
    } catch (err) {
      setResult({ error: err.message })
    } finally {
      setImporting(false)
    }
  }

  function update(i, field, value) {
    setSkipped((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)))
  }

  async function addBack(i) {
    const r = skipped[i]
    try {
      await createExpense({
        date: r.date,
        category: r.category,
        subcategory: r.subcategory,
        description: r.description,
        amount: parseFloat(r.amount),
        quantity: parseFloat(r.quantity) || 1,
        unit: r.unit || 'Count',
        shop: r.shop,
        brand: r.brand,
        currency: r.currency || undefined,
      })
      setSkipped((prev) => prev.filter((_, idx) => idx !== i))
      if (onImported) await onImported()
    } catch (err) {
      update(i, 'reason', err.message)
    }
  }

  return (
    <>
      <section className="panel">
        <h2>Expense file</h2>
        <p className="subtitle">
          Import a CSV or Excel file in this app’s expense format (the one Export produces; the old dashboard format works
          too). Duplicates are skipped. For a file from your bank, use the Bank statement tab instead.
        </p>
        <form className="add-form" onSubmit={submit}>
          <input type="file" aria-label="Expense file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files[0] || null)} />
          <select aria-label="Currency for imported rows" value={currency} onChange={(e) => setCurrency(e.target.value)} title="Currency for imported rows">
            <option value="">Currency: from file</option>
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button type="submit" disabled={!file || importing}>
            {importing ? 'Importing…' : 'Import'}
          </button>
        </form>
        {result && (
          <div className={result.error ? 'auth-error' : 'ok-note'} style={{ marginTop: '0.75rem' }} role="status">
            {result.error
              ? result.error
              : `Imported ${result.added} · skipped ${result.skipped}` +
                (result.errors && result.errors.length ? ` · ${result.errors.length} row error(s)` : '')}
          </div>
        )}
      </section>

      {skipped.length > 0 && (
        <section className="panel">
          <h2>⚠️ Skipped rows ({skipped.length})</h2>
          <p className="subtitle">Fix any values and add them back individually.</p>
          <datalist id="file-import-categories">
            {(options?.categories || []).map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
          <datalist id="file-import-shops">
            {(options?.shops || []).map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          <table className="table">
            <thead>
              <tr>
                <th>Reason</th>
                <th>Date</th>
                <th>Category</th>
                <th>Subcat</th>
                <th>Shop</th>
                <th>Item name</th>
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
                    <input type="date" aria-label={`Row ${i + 1} date`} value={r.date} onChange={(e) => update(i, 'date', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" list="file-import-categories" value={r.category} onChange={(e) => update(i, 'category', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" value={r.subcategory} onChange={(e) => update(i, 'subcategory', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" list="file-import-shops" value={r.shop} onChange={(e) => update(i, 'shop', e.target.value)} />
                  </td>
                  <td>
                    <input type="text" value={r.description} onChange={(e) => update(i, 'description', e.target.value)} />
                  </td>
                  <td className="right">
                    <input type="number" className="amount-input" value={r.quantity} onChange={(e) => update(i, 'quantity', e.target.value)} />
                  </td>
                  <td>
                    <UnitSelect value={r.unit} units={units} onChange={(u) => update(i, 'unit', u)} />
                  </td>
                  <td>
                    <input type="text" className="unit-input" value={r.currency} onChange={(e) => update(i, 'currency', e.target.value)} />
                  </td>
                  <td className="right">
                    <input type="number" className="amount-input" aria-label={`Row ${i + 1} amount`} value={r.amount} onChange={(e) => update(i, 'amount', e.target.value)} />
                  </td>
                  <td className="right nowrap">
                    <button className="icon-btn save" onClick={() => addBack(i)} title="Add this row">
                      ✓
                    </button>
                    <button className="delete-btn" onClick={() => setSkipped((prev) => prev.filter((_, idx) => idx !== i))} title="Dismiss">
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  )
}

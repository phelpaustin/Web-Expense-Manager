import UnitSelect from '../UnitSelect.jsx'
import CurrencySelect from '../CurrencySelect.jsx'
import { money } from '../../format.js'
import { viewReceipt } from '../../api/client.js'
import { SPACE_TYPE_ICONS } from './shared.jsx'

export default function AddExpensePanel({
  form,
  setForm,
  saving,
  options,
  onError,
  defaultCurrency,
  effectiveCurrency,
  billMode,
  billItems,
  submittingBill,
  receiptTotal,
  setReceiptTotal,
  categorySuggestion,
  autoCatBusy,
  autoCatResult,
  itemisingBill,
  allSpaces,
  applySuggestion,
  handleAutoCategorize,
  billTotal,
  receiptTotalNum,
  billMismatch,
  toggleBillMode,
  handleFormSubmit,
  removeBillItem,
  editBillItem,
  handleSubmitBill,
}) {
  return (
    <section className="panel" id="add-expense-panel">
      <h2>➕ Add expense</h2>
      {itemisingBill && (
        <div className="itemising-banner" role="status">
          <div className="grow">
            <strong>
              {itemisingBill.reitemise ? 'Editing items' : 'Itemising'}: {itemisingBill.shop}
            </strong>{' '}
            · {itemisingBill.date} · {money(itemisingBill.amount, itemisingBill.currency)}
            <small>
              {itemisingBill.reitemise
                ? "Change, remove or add items below. Saving replaces this bill's current items, so nothing is counted twice."
                : itemisingBill.status === 'total_only'
                  ? 'Its single total line is replaced by these items when you submit, so nothing is counted twice.'
                  : 'This bill becomes itemised when you submit its items.'}
            </small>
          </div>
          {itemisingBill.has_receipt !== false && (
            <button
              type="button"
              className="ghost-btn"
              onClick={() => viewReceipt(itemisingBill.id).catch((err) => onError?.(err.message))}
            >
              📎 View receipt
            </button>
          )}
          <button type="button" className="ghost-btn" onClick={toggleBillMode}>
            Cancel
          </button>
        </div>
      )}
      <div className="auto-cat-row">
        <button type="button" className="ghost-btn" onClick={toggleBillMode}>
          {billMode ? (itemisingBill ? '✕ Cancel itemising' : '✕ Exit bill mode') : '🧾 Add by bill'}
        </button>
        {billMode && (
          <span className="subtitle">
            Add every item from one receipt, then submit them all together. Date/shop/currency/space are shared by the whole bill.
          </span>
        )}
      </div>
      <form className="add-form" onSubmit={handleFormSubmit}>
        <input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
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
        <input type="text" placeholder="Brand" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />
        <input
          type="text"
          placeholder="Item name"
          aria-label="Item name"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        <label className="field-label">
          <span>Quantity</span>
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Qty"
            className="qty-input"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
          />
        </label>
        <label className="field-label">
          <span>Unit</span>
          <UnitSelect value={form.unit} units={options.units} onChange={(u) => setForm({ ...form, unit: u })} />
        </label>
        <CurrencySelect
          value={form.currency}
          onChange={(c) => setForm({ ...form, currency: c })}
          currencies={options.currencies}
          defaultCurrency={defaultCurrency}
          disabled={billMode && (Boolean(itemisingBill) || billItems.length > 0)}
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
                    <th>Item name</th>
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
                        <button
                          className="icon-btn"
                          onClick={() => editBillItem(i)}
                          title="Edit this item"
                          aria-label={`Edit ${it.description || it.category}`}
                        >
                          ✎
                        </button>
                        <button
                          className="delete-btn"
                          onClick={() => removeBillItem(i)}
                          title="Remove"
                          aria-label={`Remove ${it.description || it.category}`}
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="bill-total-row">
                <strong>
                  Bill total so far: {money(billTotal, effectiveCurrency)} ({billItems.length} item
                  {billItems.length === 1 ? '' : 's'})
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
                    : `⚠️ Items add up to ${money(billTotal, effectiveCurrency)}, ${billMismatch > 0 ? 'more than' : 'less than'} the receipt total ` +
                      `of ${money(receiptTotalNum, effectiveCurrency)} (off by ${money(Math.abs(billMismatch), effectiveCurrency)}).`}
                </p>
              )}
              <button type="button" className="primary-btn" onClick={handleSubmitBill} disabled={submittingBill}>
                {submittingBill ? 'Submitting…' : `✅ Submit bill (${money(billTotal, effectiveCurrency)})`}
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
    </section>
  )
}

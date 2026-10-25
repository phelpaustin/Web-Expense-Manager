import UnitSelect from '../UnitSelect.jsx'
import CurrencySelect from '../CurrencySelect.jsx'
import { TotalOnlyBadge } from '../BillStatus.jsx'
import { money } from '../../format.js'
import { SPACE_TYPE_ICONS, SelectBox } from './shared.jsx'

export function ExpenseRow({
  e,
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
}) {
  if (editingId === e.id) {
    return (
      <tr key={e.id} className="editing">
        <td colSpan={COLS}>
          <div className="edit-grid">
            <label className="edit-field">
              <span>Date</span>
              <input type="date" value={editForm.date} onChange={(ev) => setEditForm({ ...editForm, date: ev.target.value })} />
            </label>
            <label className="edit-field">
              <span>Category</span>
              <input
                type="text"
                list="cat-options"
                value={editForm.category}
                onChange={(ev) => setEditForm({ ...editForm, category: ev.target.value })}
              />
            </label>
            <label className="edit-field">
              <span>Subcategory</span>
              <input
                type="text"
                list="subcat-edit-options"
                value={editForm.subcategory}
                onChange={(ev) => setEditForm({ ...editForm, subcategory: ev.target.value })}
              />
            </label>
            <label className="edit-field">
              <span>Shop</span>
              <input
                type="text"
                list="shop-options"
                value={editForm.shop}
                onChange={(ev) => setEditForm({ ...editForm, shop: ev.target.value })}
              />
            </label>
            <label className="edit-field edit-field--wide">
              <span>Item name</span>
              <input
                type="text"
                value={editForm.description}
                onChange={(ev) => setEditForm({ ...editForm, description: ev.target.value })}
              />
            </label>
            {allSpaces.length > 0 && (
              <label className="edit-field">
                <span>Space</span>
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
              </label>
            )}
            <label className="edit-field">
              <span>Quantity</span>
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={editForm.quantity}
                onChange={(ev) => setEditForm({ ...editForm, quantity: ev.target.value })}
              />
            </label>
            <label className="edit-field">
              <span>Unit</span>
              <UnitSelect value={editForm.unit} units={options.units} onChange={(u) => setEditForm({ ...editForm, unit: u })} />
            </label>
            <label className="edit-field">
              <span>Amount</span>
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={editForm.amount}
                onChange={(ev) => setEditForm({ ...editForm, amount: ev.target.value })}
              />
            </label>
            <label className="edit-field">
              <span>Currency</span>
              <CurrencySelect
                value={editForm.currency}
                onChange={(c) => setEditForm({ ...editForm, currency: c })}
                currencies={options.currencies}
                allowDefault={false}
              />
            </label>
          </div>
          <div className="edit-actions">
            <button className="icon-btn save" onClick={() => afterMutation(saveEdit(e.id))} title="Save">
              ✓ Save
            </button>
            <button className="icon-btn" onClick={cancelEdit} title="Cancel">
              ✕ Cancel
            </button>
          </div>
        </td>
      </tr>
    )
  }
  return (
    <tr
      key={e.id}
      className={`${e.bill_total_only ? 'row-total-only' : ''}${selectMode && isSelected(e.id) ? ' row-selected' : ''}`.trim()}
    >
      {selectMode && (
        <td className="select-cell">
          {canEditExpense(e) && (
            <SelectBox
              state={isSelected(e.id) ? 'all' : 'none'}
              label={`Select ${e.description || e.category}`}
              onChange={(on) => setSelected([e.id], on)}
            />
          )}
        </td>
      )}
      <td>{e.date}</td>
      <td>{e.category}</td>
      <td>{e.subcategory}</td>
      <td>{e.shop}</td>
      <td>
        {e.description}
        {e.bill_total_only && <TotalOnlyBadge />}
      </td>
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
        {canEditExpense(e) && e.bill_total_only && e.source_bill_id && (
          <button
            className="mini-btn primary"
            onClick={() => itemiseFromExpense(e)}
            title="Enter the items on this bill; they replace this single total"
          >
            Itemise
          </button>
        )}
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

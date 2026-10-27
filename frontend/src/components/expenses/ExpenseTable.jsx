import { Fragment } from 'react'
import { TotalOnlyBadge } from '../BillStatus.jsx'
import { money } from '../../format.js'
import { SelectBox } from './shared.jsx'
import { ExpenseRow } from './ExpenseRow.jsx'

export default function ExpenseTable({
  rowProps,
  selectMode,
  groupByBill,
  expandedBillKeys,
  pageExpenses,
  toggleBillGroup,
  canEditExpense,
  editableIds,
  selectionState,
  COLS,
  setSelected,
  itemiseFromExpense,
  editItemsOfBill,
  billGroups,
  onPickTrip,
}) {
  return (
    <table className="table">
      <thead>
        <tr>
          {selectMode && (
            <th className="select-cell">
              <SelectBox
                state={selectionState(editableIds)}
                label="Select all on this page"
                onChange={(on) => setSelected(editableIds, on)}
              />
            </th>
          )}
          <th>Date</th>
          <th>Category</th>
          <th>Subcat</th>
          <th>Shop</th>
          <th>Item name</th>
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
              // A bill recorded as a total only (no items yet) is flagged right on its header,
              // so it is visible without expanding and can be itemised from there.
              const totalOnlyItems = group.items.filter((e) => e.bill_total_only)
              const allTotalOnly = totalOnlyItems.length === group.items.length
              const single = group.items.length === 1 ? group.items[0] : null
              // Items that all came from one itemised bill can be re-opened for editing.
              const billIds = new Set(group.items.map((e) => e.source_bill_id))
              const itemisedBillId = totalOnlyItems.length === 0 && billIds.size === 1 ? [...billIds][0] : null
              // A single line with no shop is named after what it is, like its bill on the Bills page.
              const name = group.shop || (single ? single.description : '') || 'No shop'
              const groupEditableIds = group.items.filter(canEditExpense).map((e) => e.id)
              return (
                <Fragment key={group.key}>
                  <tr
                    className={`bill-group-header clickable-row${allTotalOnly ? ' row-total-only' : ''}`}
                    onClick={() => toggleBillGroup(group.key)}
                  >
                    <td colSpan={COLS}>
                      {selectMode && groupEditableIds.length > 0 && (
                        <SelectBox
                          state={selectionState(groupEditableIds)}
                          label={`Select ${name}`}
                          onChange={(on) => setSelected(groupEditableIds, on)}
                        />
                      )}{' '}
                      {isExpanded ? '▾' : '▸'} 🧾 {group.date} · {name} · {group.items.length} item
                      {group.items.length === 1 ? '' : 's'} · Bill total:{' '}
                      {money(
                        group.items.reduce((sum, e) => sum + e.amount, 0),
                        group.currency,
                      )}
                      {totalOnlyItems.length > 0 && <TotalOnlyBadge />}
                      {itemisedBillId && group.items.every(canEditExpense) && (
                        <button
                          type="button"
                          className="mini-btn"
                          onClick={(ev) => {
                            ev.stopPropagation()
                            editItemsOfBill(itemisedBillId)
                          }}
                          title="Change, add or remove the items on this bill"
                        >
                          Edit items
                        </button>
                      )}
                      {onPickTrip && groupEditableIds.length > 0 && rowProps.allSpaces.some((g) => g.role !== 'viewer') && (
                        <button
                          type="button"
                          className="mini-btn"
                          onClick={(ev) => {
                            ev.stopPropagation()
                            onPickTrip(groupEditableIds, `${name} · ${group.date}`)
                          }}
                          title="Move or copy this whole bill to a trip"
                          aria-label={`Move or copy ${name} to a trip`}
                        >
                          ✈ To trip
                        </button>
                      )}
                      {allTotalOnly && single && single.source_bill_id && canEditExpense(single) && (
                        <button
                          type="button"
                          className="mini-btn primary"
                          onClick={(ev) => {
                            ev.stopPropagation()
                            itemiseFromExpense(single)
                          }}
                          title="Enter the items on this bill; they replace this single total"
                        >
                          Itemise
                        </button>
                      )}
                    </td>
                  </tr>
                  {isExpanded && group.items.map((e) => <ExpenseRow key={e.id} e={e} {...rowProps} />)}
                </Fragment>
              )
            })
          : pageExpenses.map((e) => <ExpenseRow key={e.id} e={e} {...rowProps} />)}
      </tbody>
    </table>
  )
}

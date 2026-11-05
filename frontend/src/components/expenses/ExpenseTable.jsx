import { Fragment } from 'react'
import { money } from '../../format.js'
import { categorySummary } from '../../billGroups.js'
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
          <th>Space</th>
          <th className="right">Amount</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {groupByBill
          ? billGroups.map((group) => {
              const isExpanded = expandedBillKeys.has(group.key)
              const single = group.items.length === 1 ? group.items[0] : null
              // Items that all came from one itemised bill can be re-opened for editing.
              const billIds = new Set(group.items.map((e) => e.source_bill_id))
              const itemisedBillId = group.items.length > 1 && billIds.size === 1 ? [...billIds][0] : null
              // A single line with no shop is named after what it is, like its bill on the Bills page.
              const name = group.shop || (single ? single.description : '') || 'No shop'
              const groupEditableIds = group.items.filter(canEditExpense).map((e) => e.id)
              return (
                <Fragment key={group.key}>
                  <tr
                    className="bill-group-header clickable-row"
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
                      <button
                        type="button"
                        className="chevron-btn"
                        aria-expanded={isExpanded}
                        aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${name}`}
                        onClick={(ev) => {
                          ev.stopPropagation()
                          toggleBillGroup(group.key)
                        }}
                      >
                        {isExpanded ? '▾' : '▸'}
                      </button>{' '}
                      🧾 {group.date} · {name}
                      {group.items.length > 1 && ` · ${group.items.length} items`} · {categorySummary(group.items)} · Bill total:{' '}
                      {money(
                        group.items.reduce((sum, e) => sum + e.amount, 0),
                        group.currency,
                      )}
                      {single && canEditExpense(single) && (
                        <button
                          type="button"
                          className="mini-btn"
                          onClick={(ev) => {
                            ev.stopPropagation()
                            // The editor opens inside the bill's rows, so open the bill first.
                            if (!isExpanded) toggleBillGroup(group.key)
                            rowProps.startEdit(single)
                          }}
                          title="Edit the category, space and every other detail"
                          aria-label={`Edit ${name}`}
                        >
                          ✎ Edit
                        </button>
                      )}
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

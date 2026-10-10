// The three states a bill moves through, plus the marker shown on the Expenses page
// for an expense that is only a bill's total (not yet broken into items).
export const BILL_STATUS = {
  pending: { label: 'To itemise', hint: 'Not counted as spending yet. Record its total or itemise it.' },
  total_only: { label: 'Total only', hint: 'Counted as one expense for the whole amount. You can itemise it any time.' },
  itemised: { label: 'Itemised', hint: 'Broken down into its line items.' },
}

export function BillStatusChip({ status, itemCount = 0 }) {
  const info = BILL_STATUS[status] || { label: status, hint: '' }
  const label = status === 'itemised' && itemCount > 0 ? `${info.label} · ${itemCount} item${itemCount === 1 ? '' : 's'}` : info.label
  return (
    <span className={`status-chip status-${status}`} title={info.hint}>
      {label}
    </span>
  )
}

export function TotalOnlyBadge() {
  return (
    <span className="total-only-badge" title="Entered from a bill total with no item breakdown. Click Itemise to add the items; the total stays counted until you do.">
      🧾 Total only
    </span>
  )
}

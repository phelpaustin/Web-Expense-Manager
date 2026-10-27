// Presentation helpers for the "Worth a look" panel. No React, so they are easy to test.
import { money } from './format.js'

// "Rent" or "Rent at ICA": what the entry is, as briefly as the data allows.
export function entryName(e) {
  const what = e.description || e.category || 'Expense'
  return e.shop && e.shop !== e.description ? `${what} at ${e.shop}` : what
}

// "4.2× your usual" with one decimal, none when it is a whole number.
export function ratioText(ratio) {
  const r = Math.round(ratio * 10) / 10
  return `${Number.isInteger(r) ? r : r.toFixed(1)}×`
}

export function describeUnusual(i) {
  return `${entryName(i)} on ${i.date}, ${money(i.amount)}, is ${ratioText(i.ratio)} your usual ${i.category} expense of about ${money(i.usual)}.`
}

export function describeDuplicate(d) {
  return `${d.count} entries of ${entryName(d)} for ${money(d.amount)} on ${d.date}.`
}

// Said when there is nothing to list.
export function allClearText(data) {
  const u = data.unusual
  const checked = u.checked === 1 ? '1 expense' : `${u.checked} expenses`
  return `Nothing stands out: ${checked} from the last ${u.recent_days} days checked against your usual spending, and no repeated entries in the last ${data.duplicates.recent_days} days.`
}

// The panel stays out of the way when there is nothing to say and nothing was checked.
export function hasFindings(data) {
  return data.unusual.items.length > 0 || data.duplicates.items.length > 0
}

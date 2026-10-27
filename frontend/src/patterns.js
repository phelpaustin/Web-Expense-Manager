// Presentation helpers for the "When you spend" panel. No React, so they are easy to test.
import { money } from './format.js'

export const WINDOWS = [
  { months: 3, label: 'Last 3 months' },
  { months: 6, label: 'Last 6 months' },
  { months: 12, label: 'Last 12 months' },
]

// A bar's width as a whole percent of the longest one; any spending at all keeps a visible sliver.
export function barPercent(value, max) {
  if (!(max > 0) || !(value > 0)) return 0
  return Math.max(2, Math.round((value / max) * 100))
}

// The bar rows of one list: each row with its width, and whether it is the top one.
export function withBars(rows) {
  const max = Math.max(0, ...rows.map((r) => Number(r.per_day)))
  return rows.map((r) => ({ ...r, percent: barPercent(Number(r.per_day), max), peak: max > 0 && Number(r.per_day) === max }))
}

export function describeRow(row, noun) {
  return `${row.name || `Days ${row.label}`}: about ${money(row.per_day)} a day, ${row.share_pct}% of ${noun} spending.`
}

export function rowLabel(row) {
  return row.name || `Days ${row.label}`
}

// What to say above the bars. Empty while there is no conclusion to draw.
export function headline(data) {
  if (!data.enough) return ''
  const byDay = Object.fromEntries(data.weekdays.map((w) => [w.name, w]))
  const parts = [`You spend the most on ${data.busiest_weekday}s (about ${money(byDay[data.busiest_weekday].per_day)} a day) and the least on ${data.quietest_weekday}s (${money(byDay[data.quietest_weekday].per_day)}).`]
  const w = data.weekend
  if (w && w.ratio != null && w.ratio >= 1.25) parts.push(`Weekend days cost ${w.ratio}× a weekday.`)
  else if (w && w.ratio != null && w.ratio <= 0.8) parts.push(`Weekdays cost ${Math.round((1 / w.ratio) * 10) / 10}× a weekend day.`)
  return parts.join(' ')
}

// Said when there is too little spending to see a pattern in.
export function notEnoughText(data) {
  const n = data.count
  return `Not enough spending to see a pattern yet: ${n} ${n === 1 ? 'expense' : 'expenses'} over ${data.days} days. It needs at least 20 expenses over 4 weeks. Recurring payments are left out.`
}

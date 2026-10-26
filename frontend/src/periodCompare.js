// Presentation helpers for the "compared with" tiles on Insights, Overview. No React, so they are easy to test.
import { money } from './format.js'
import { monthLabel, monthShort, ordinal } from './categoryChange.js'

// What a tile is measured against: "Sep 2026", or "Jun, Jul and Aug" for the average.
export function comparedWith(row) {
  if (row.key === 'average') {
    const names = (row.months || []).slice().sort().map(monthShort)
    if (names.length <= 1) return names.join('')
    return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
  }
  return row.month ? monthLabel(row.month) : ''
}

// '+12%' / '-8%' / '0%', or '' when a percentage cannot be given (nothing to compare with).
export function pctText(row) {
  if (row.pct_change == null) return ''
  const n = Number(row.pct_change)
  return `${n > 0 ? '+' : ''}${n}%`
}

// One sentence for a tile, used as its readable summary.
export function describeRow(row, total) {
  if (!row.available) return `${row.label}: not enough history yet.`
  const change = Number(row.change)
  if (change === 0) return `${row.label}: unchanged at ${money(total)}.`
  const pct = pctText(row)
  return `${row.label}: ${change > 0 ? 'up' : 'down'} ${money(Math.abs(change))}${pct ? ` (${pct})` : ''}, ${money(total)} against ${money(row.before)}.`
}

// The note under the tiles while the chosen month is still going on.
export function partialNote(data) {
  if (!data.partial) return ''
  return `${monthLabel(data.month)} so far (to the ${ordinal(data.through_day)}), against the same days of each earlier month.`
}

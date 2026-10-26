// Presentation helpers for the "Recurring costs" panel. No React, so they are easy to test.
import { money } from './format.js'
import { monthShort } from './categoryChange.js'

// '2026-11-01' -> '1 Nov 2026'
export function dayLabel(iso) {
  if (!iso) return ''
  return `${Number(iso.slice(8, 10))} ${monthShort(iso.slice(0, 7))} ${iso.slice(0, 4)}`
}

// When the next payment is due; a date in the past is overdue.
export function dueText(item) {
  if (!item.next_due) return ''
  return item.overdue ? `Overdue since ${dayLabel(item.next_due)}` : dayLabel(item.next_due)
}

// 'Up 20% since 1 Sep 2026 (SEK 100.00 to SEK 120.00)', in the template's own currency.
export function priceChangeText(change) {
  if (!change) return ''
  const pct = change.pct_change == null ? '' : ` ${Math.abs(change.pct_change)}%`
  return `${change.direction === 'up' ? 'Up' : 'Down'}${pct} since ${dayLabel(change.since)} (${money(change.from, change.currency)} to ${money(change.to, change.currency)})`
}

// The headline: how many payments, and what they come to.
export function headline(data) {
  const n = data.count
  if (n === 0) return 'No recurring payments yet.'
  return `${n} recurring ${n === 1 ? 'payment costs' : 'payments cost'} about ${money(data.monthly_total)} a month (${money(data.yearly_total)} a year).`
}

// Per-payment frequency in words for the table.
export function perText(frequency) {
  return { Daily: 'a day', Weekly: 'a week', 'Bi-weekly': 'every 2 weeks', Monthly: 'a month', Quarterly: 'a quarter', Yearly: 'a year' }[frequency] || frequency
}

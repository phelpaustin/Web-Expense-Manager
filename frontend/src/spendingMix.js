// Presentation helpers for the "committed / everyday / one-off" panel, kept free of React so
// they are easy to test.
import { money } from './format.js'
import { monthShort } from './categoryChange.js'

export const MONTH_CHOICES = [
  { months: 3, label: 'Last 3 months' },
  { months: 6, label: 'Last 6 months' },
  { months: 12, label: 'Last 12 months' },
]
export const DEFAULT_MONTHS = 12

// Chart colours: committed is the calm base, one-offs stand out.
export const MIX_COLORS = { committed: '#6d7bff', everyday: '#10b981', oneOff: '#f59e0b' }

// '2026-01-12' -> '12 Jan'
export function dayLabel(iso) {
  const [year, month, day] = iso.split('-')
  return `${Number(day)} ${monthShort(`${year}-${month}`)}`
}

// One bar per month. A month still in progress is starred, since it is not a full month yet.
export function chartRows(data) {
  return data.months.map((m) => ({
    name: `${monthShort(m.month)}${m.partial ? '*' : ''}`,
    month: m.month,
    partial: m.partial,
    committed: Number(m.committed),
    everyday: Number(m.everyday),
    oneOff: Number(m.one_off),
    total: Number(m.total),
  }))
}

// The one-line answer: what a normal month costs, and what one-offs added on top.
export function describeMix(data) {
  if (!data.available) return 'No spending recorded in this period.'
  const t = data.totals
  const n = data.one_off_count
  const oneOffs = n > 0 ? ` One-off purchases added ${money(t.one_off)} (${n} ${n === 1 ? 'purchase' : 'purchases'}).` : ''
  if (data.typical) {
    const typ = data.typical
    return `A typical month is about ${money(typ.baseline)}: ${money(typ.committed)} committed and ${money(typ.everyday)} everyday.${oneOffs}`
  }
  return `So far ${money(t.total)}: ${money(t.committed)} committed, ${money(t.everyday)} everyday and ${money(t.one_off)} in one-offs. A typical month needs two finished months.`
}

// One line about a flagged purchase: what it was and how unusual it is.
export function describeOneOff(o) {
  const name = o.description || o.category
  const usual = o.basis === 'category' ? `${o.category} purchase` : 'purchase'
  return `${name}: ${money(o.amount)} on ${dayLabel(o.date)}, ${o.ratio}× your usual ${usual} (${money(o.usual)})`
}

// One line about a commitment: what it is, what it has cost, how often.
export function describeCommitment(c) {
  return `${c.description}: ${money(c.total)} (${c.count} ${c.count === 1 ? 'payment' : 'payments'}, last ${dayLabel(c.last_date)})`
}

// Why a purchase is called a one-off, from the rule the server used.
export function describeRule(rule) {
  return `A purchase counts as a one-off when it is more than ${rule.multiple}× what you usually spend on that category, judged on your last year of purchases. A category with fewer than ${rule.min_samples} purchases is compared with your purchases overall.`
}

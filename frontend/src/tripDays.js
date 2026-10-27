// Day-by-day view of a trip: which expense falls on which "Day N", and how a multi-day cost is shared.

const MAX_DAYS = 366
const DAY_MS = 86400000

const parse = (iso) => {
  const [y, m, d] = String(iso || '').split('-').map(Number)
  return y && m && d ? Date.UTC(y, m - 1, d) : NaN
}
const fmt = (ms) => new Date(ms).toISOString().slice(0, 10)

// The days of a trip: [{ n: 1, date: '2026-06-25' }, …]. Empty when the trip has no usable dates.
export function dayList(start, end) {
  const a = parse(start)
  const b = parse(end)
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return []
  const count = Math.min(Math.round((b - a) / DAY_MS) + 1, MAX_DAYS)
  return Array.from({ length: count }, (_, i) => ({ n: i + 1, date: fmt(a + i * DAY_MS) }))
}

// "25 Jun" for display.
export function shortDate(iso) {
  const ms = parse(iso)
  return Number.isNaN(ms) ? String(iso || '') : new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

export function dayLabel(day) {
  return `Day ${day.n} · ${shortDate(day.date)}`
}

// Every date an expense covers: its stretch of the trip when set, otherwise the day it was paid.
export function coveredDates(expense) {
  if (expense.covers_from && expense.covers_to) {
    const a = parse(expense.covers_from)
    const b = parse(expense.covers_to)
    if (!Number.isNaN(a) && !Number.isNaN(b) && b >= a) {
      return Array.from({ length: Math.min(Math.round((b - a) / DAY_MS) + 1, MAX_DAYS) }, (_, i) => fmt(a + i * DAY_MS))
    }
  }
  return [expense.date]
}

// Share whole cents over `parts` days so the shares always add up to the total exactly.
export function splitCents(totalCents, parts) {
  const base = Math.trunc(totalCents / parts)
  const extra = totalCents - base * parts
  return Array.from({ length: parts }, (_, i) => base + (i < extra ? 1 : 0))
}

const toCents = (v) => (v === null || v === undefined || v === '' ? null : Math.round(Number(v) * 100))

// Lay the expenses out over the days. Amounts are in the trip's currency; an expense with no
// exchange rate is listed but left out of the totals. Anything on a date outside the trip goes to
// `outside` (a stay paid before the trip, say) so nothing silently disappears.
export function planByDay(expenses, days) {
  const byDate = new Map(days.map((d) => [d.date, { ...d, items: [], cents: 0 }]))
  const outside = { items: [], cents: 0 }
  for (const expense of expenses) {
    const dates = coveredDates(expense)
    const cents = toCents(expense.amount_in_trip_currency)
    const shares = cents === null ? dates.map(() => null) : splitCents(cents, dates.length)
    dates.forEach((date, i) => {
      const item = { expense, date, cents: shares[i], parts: dates.length, totalCents: cents, spread: dates.length > 1 }
      const slot = byDate.get(date) || outside
      slot.items.push(item)
      if (shares[i] !== null) slot.cents += shares[i]
    })
  }
  return { days: [...byDate.values()], outside }
}

// "Day 1–3", "Day 4", or the dates when they fall outside the trip.
export function daysLabel(expense, days) {
  const number = new Map(days.map((d) => [d.date, d.n]))
  const dates = coveredDates(expense)
  const first = number.get(dates[0])
  const last = number.get(dates[dates.length - 1])
  if (first === undefined || last === undefined) {
    return dates.length > 1 ? `${shortDate(dates[0])} – ${shortDate(dates[dates.length - 1])}` : shortDate(dates[0])
  }
  return first === last ? `Day ${first}` : `Day ${first}–${last}`
}

export function isPlaced(expense, days) {
  return coveredDates(expense).every((d) => days.some((x) => x.date === d))
}

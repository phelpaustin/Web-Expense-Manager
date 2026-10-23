// Sums the per-month category rows the dashboard returns ({ month: 'YYYY-MM', category, total })
// for the period the user picked. Months are 'YYYY-MM' strings, which sort the same as dates.

export const PERIOD_PRESETS = [
  { value: 'this_month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: 'last_3', label: 'Last 3 months' },
  { value: 'last_12', label: 'Last 12 months' },
  { value: 'this_year', label: 'This year' },
  { value: 'last_year', label: 'Last year' },
  { value: 'all', label: 'All time' },
]
export const PICK_MONTH = 'pick_month'
export const PICK_YEAR = 'pick_year'

const pad = (n) => String(n).padStart(2, '0')
export const monthKey = (year, month) => `${year}-${pad(month)}` // month is 1-12

// The month `back` months before the given one.
function shiftMonth(year, month, back) {
  const index = year * 12 + (month - 1) - back
  return monthKey(Math.floor(index / 12), (index % 12) + 1)
}

// Inclusive [from, to] month keys for a period, or null for no limit.
export function periodRange(period, value, today = new Date()) {
  const y = today.getFullYear()
  const m = today.getMonth() + 1
  switch (period) {
    case 'this_month':
      return [monthKey(y, m), monthKey(y, m)]
    case 'last_month': {
      const k = shiftMonth(y, m, 1)
      return [k, k]
    }
    case 'last_3':
      return [shiftMonth(y, m, 2), monthKey(y, m)]
    case 'last_12':
      return [shiftMonth(y, m, 11), monthKey(y, m)]
    case 'this_year':
      return [monthKey(y, 1), monthKey(y, 12)]
    case 'last_year':
      return [monthKey(y - 1, 1), monthKey(y - 1, 12)]
    case PICK_MONTH:
      return value ? [value, value] : null
    case PICK_YEAR:
      return value ? [`${value}-01`, `${value}-12`] : null
    default:
      return null
  }
}

// Months (newest first) and years (newest first) that have any spending, for the pickers.
export function availablePeriods(rows) {
  const months = [...new Set((rows || []).map((r) => r.month))].sort().reverse()
  const years = [...new Set(months.map((k) => k.slice(0, 4)))]
  return { months, years }
}

// Per-category totals for the period, biggest first, with each category's share of the period.
export function categoryTotals(rows, period, value, today = new Date()) {
  const range = periodRange(period, value, today)
  const sums = new Map()
  for (const r of rows || []) {
    if (range && (r.month < range[0] || r.month > range[1])) continue
    sums.set(r.category, (sums.get(r.category) || 0) + Number(r.total))
  }
  const total = [...sums.values()].reduce((a, b) => a + b, 0)
  return [...sums.entries()]
    .map(([category, sum]) => ({
      category,
      total: Math.round(sum * 100) / 100,
      pct_of_total: total ? Math.round((sum / total) * 1000) / 10 : 0,
    }))
    .sort((a, b) => b.total - a.total)
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export function monthLabel(key) {
  const [y, m] = key.split('-')
  return `${MONTH_NAMES[Number(m) - 1]} ${y}`
}

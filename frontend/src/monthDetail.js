// Helpers for the month drill-down: click a month on a chart to see its expenses and income.

const pad = (n) => String(n).padStart(2, '0')

export function isMonthKey(value) {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(String(value || ''))
}

// "2025-02" -> { from: "2025-02-01", to: "2025-02-28" }
export function monthRange(month) {
  const [y, m] = month.split('-').map(Number)
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate()
  return { from: `${y}-${pad(m)}-01`, to: `${y}-${pad(m)}-${pad(last)}` }
}

// "2025-12", +1 -> "2026-01"
export function shiftMonth(month, delta) {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(Date.UTC(y, m - 1 + delta, 1))
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`
}

// "2025-01" -> "January 2025"
export function monthTitle(month) {
  const [y, m] = month.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

export function currentMonthKey(now = new Date()) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}`
}

export function incomeInMonth(rows, month) {
  return (rows || [])
    .filter((r) => String(r.date).slice(0, 7) === month)
    .sort((a, b) => String(b.date).localeCompare(String(a.date)) || b.id - a.id)
}

// Totals per currency. Rows keep their own currency, so mixed currencies are not added together.
// Summed in whole cents so amounts never pick up float noise.
export function totalsByCurrency(rows) {
  const cents = new Map()
  for (const r of rows || []) {
    cents.set(r.currency, (cents.get(r.currency) || 0) + Math.round(Number(r.amount || 0) * 100))
  }
  return [...cents].map(([currency, c]) => ({ currency, total: c / 100 }))
}

// Income belongs to the person, not to a shared space, so it only shows for the personal view.
export function includesIncome(scope, spaceIds) {
  if (spaceIds && spaceIds.length > 0) return spaceIds.includes('personal')
  return !scope || scope === 'all' || scope === 'personal'
}

// Same space selection the dashboard uses, as /api/expenses filters.
export function scopeFilters(scope, spaceIds) {
  if (spaceIds && spaceIds.length > 0) return { space_ids: spaceIds.join(',') }
  return scope && scope !== 'all' ? { scope } : {}
}

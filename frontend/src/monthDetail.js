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

// ── Editing an expense inside the dialog ──────────────────

export function editFormFor(expense) {
  return {
    date: expense.date,
    description: expense.description || '',
    shop: expense.shop || '',
    category: expense.category || '',
    amount: String(expense.amount),
    currency: expense.currency || '',
  }
}

// Only the fields that changed. The server updates just those, so quantity, unit, brand and the
// rest stay as they were. Returns { error } for input the server would refuse, { changes: {} } for none.
export function expenseChanges(original, form) {
  if (!form.date) return { error: 'Enter a date.' }
  if (!form.category.trim()) return { error: 'Enter a category.' }
  const amount = parseFloat(form.amount)
  if (!Number.isFinite(amount) || amount <= 0) return { error: 'Enter an amount greater than zero.' }

  const changes = {}
  if (form.date !== original.date) changes.date = form.date
  for (const key of ['description', 'shop', 'category']) {
    if (form[key].trim() !== String(original[key] || '').trim()) changes[key] = form[key].trim()
  }
  if (Math.round(amount * 100) !== Math.round(Number(original.amount) * 100)) changes.amount = amount
  if (form.currency && form.currency !== original.currency) changes.currency = form.currency
  return { changes }
}

// Read-only spaces (viewer role) can't be changed; personal expenses always can.
export function canEditExpense(expense, spaces) {
  if (!expense.group_id) return true
  return (spaces || []).find((g) => g.id === expense.group_id)?.role !== 'viewer'
}

// ── Moving expenses into a trip ───────────────────────────

const TRIP_CATEGORIES = new Set(['trip', 'trips'])

// Statement rows categorised "Trip" that aren't in a trip yet.
export function tripCategoryIds(expenses) {
  return (expenses || [])
    .filter((e) => !e.group_id && TRIP_CATEGORIES.has(String(e.category || '').trim().toLowerCase()))
    .map((e) => e.id)
}

// Trips the person may add expenses to (viewers may not).
export function movableTrips(trips) {
  return (trips || []).filter((t) => t.role !== 'viewer')
}

export function spaceName(expense, spaces) {
  if (!expense.group_id) return ''
  return (spaces || []).find((g) => g.id === expense.group_id)?.name || ''
}

// The <select> value: "" = nothing chosen, "personal" = back to personal, otherwise a trip id.
export function moveChanges(choice) {
  if (choice === 'personal') return { group_id: null }
  const id = parseInt(choice, 10)
  return Number.isInteger(id) ? { group_id: id } : null
}

export function copiedMessage({ copied, skipped }, choice, trips) {
  const name = (trips || []).find((t) => String(t.id) === String(choice))?.name || 'the trip'
  const noun = copied === 1 ? 'expense' : 'expenses'
  const already = skipped ? ` ${skipped} already there, skipped.` : ''
  return `Copied ${copied} ${noun} to ${name}.${already}`
}

export function movedMessage(count, choice, trips) {
  const noun = count === 1 ? 'expense' : 'expenses'
  if (choice === 'personal') return `Moved ${count} ${noun} back to personal.`
  const name = (trips || []).find((t) => String(t.id) === String(choice))?.name
  return `Moved ${count} ${noun} to ${name || 'the trip'}.`
}

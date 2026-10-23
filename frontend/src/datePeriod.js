// A date filter that is more than "from" and "to": quick periods, a particular month or year,
// or a custom range. It turns the choice into the date_from / date_to the list endpoint takes.
import { periodRange, PICK_MONTH, PICK_YEAR, monthKey } from './categoryPeriod.js'

export const ANY_DATE = ''
export const CUSTOM_RANGE = 'custom'
export { PICK_MONTH, PICK_YEAR }

export const DATE_PRESETS = [
  { value: ANY_DATE, label: 'Any date' },
  { value: 'this_month', label: 'This month' },
  { value: 'last_month', label: 'Last month' },
  { value: 'last_3', label: 'Last 3 months' },
  { value: 'last_12', label: 'Last 12 months' },
  { value: 'this_year', label: 'This year' },
  { value: 'last_year', label: 'Last year' },
]

export const EMPTY_DATE_FILTER = { period: ANY_DATE, value: '', from: '', to: '' }

// 'YYYY-MM' -> the last calendar day of that month, as 'YYYY-MM-DD'.
export function lastDayOfMonth(key) {
  const [y, m] = key.split('-').map(Number)
  return `${key}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`
}

const validMonth = (v) => /^\d{4}-(0[1-9]|1[0-2])$/.test(v || '')
const validYear = (v) => /^\d{4}$/.test(String(v || ''))

// -> { date_from, date_to }, either '' for "no limit".
export function datesFor(filter, today = new Date()) {
  const { period, value, from, to } = filter
  if (period === CUSTOM_RANGE) return { date_from: from || '', date_to: to || '' }
  if (period === PICK_MONTH && !validMonth(value)) return { date_from: '', date_to: '' }
  if (period === PICK_YEAR && !validYear(value)) return { date_from: '', date_to: '' }
  const range = periodRange(period, value, today)
  if (!range) return { date_from: '', date_to: '' }
  return { date_from: `${range[0]}-01`, date_to: lastDayOfMonth(range[1]) }
}

// What a freshly chosen period starts with, so the month/year picker is never blank.
export function defaultValueFor(period, today = new Date()) {
  if (period === PICK_MONTH) return monthKey(today.getFullYear(), today.getMonth() + 1)
  if (period === PICK_YEAR) return String(today.getFullYear())
  return ''
}

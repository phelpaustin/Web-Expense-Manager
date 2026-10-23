// Presentation helpers for the forecast panel, kept free of React so they are easy to test.
import { money } from './format.js'
import { monthShort, monthLabel, ordinal } from './categoryChange.js'

// Chart colours: the forecast stands apart from what already happened.
export const FORECAST_COLORS = { baseline: '#6d7bff', oneOff: '#f59e0b', forecast: '#10b981' }

// Bars for the recent months (baseline, with any one-offs stacked on top), then the forecast
// month, which carries its range as [how far down, how far up] for the whisker.
export function chartRows(data) {
  const rows = data.history.map((m) => ({
    name: monthShort(m.month),
    month: m.month,
    baseline: Number(m.baseline),
    oneOff: Number(m.one_off),
    forecast: 0,
    isForecast: false,
  }))
  const point = Number(data.forecast.point)
  rows.push({
    name: `${monthShort(data.month)}*`,
    month: data.month,
    baseline: 0,
    oneOff: 0,
    forecast: point,
    error: data.forecast.low == null ? undefined : [point - Number(data.forecast.low), Number(data.forecast.high) - point],
    isForecast: true,
  })
  return rows
}

// The headline: what to expect this month, and how sure.
export function describeForecast(data) {
  if (!data.available) {
    // Tolerates a response without the usual details rather than breaking the whole dashboard.
    const minMonths = data.requirements?.min_months ?? 3
    return data.reason === 'no_spending'
      ? 'No spending recorded yet.'
      : `A forecast needs at least ${minMonths} finished months of spending; you have ${data.months_available ?? 0}.`
  }
  const req = data.requirements
  const f = data.forecast
  const month = monthLabel(data.month)
  if (f.low == null) {
    return `${month} is on track for about ${money(f.point)} (not counting one-offs). A range needs ${req.months_for_range} finished months; you have ${data.months_available}.`
  }
  return `${month} is on track for about ${money(f.point)}, most likely between ${money(f.low)} and ${money(f.high)} (not counting one-offs).`
}

// What has been spent so far this month, for comparison.
export function describeSoFar(data) {
  const s = data.so_far
  const extra = Number(s.one_off) > 0 ? `, including ${money(s.one_off)} of one-offs` : ''
  return `So far this month (to the ${ordinal(s.day)}): ${money(s.total)}${extra}.`
}

// How well the method has done on months it had not seen.
export function describeAccuracy(data) {
  const a = data.accuracy
  if (!a) return `Not enough history to test the method yet (it needs ${data.requirements.months_to_test} finished months).`
  if (a.mape == null) return `Tested on the last ${a.months_tested} months.`
  const tested = `Tested on your last ${a.months_tested} ${a.months_tested === 1 ? 'month' : 'months'}, this method was off by ${a.mape}% on average`
  const versus = a.naive_mape != null && a.beats_naive != null
    ? ` (assuming last month's spending again would have been off by ${a.naive_mape}%)`
    : ''
  const point = Number(data.forecast.point)
  const bias = Number(a.bias)
  const lean = a.months_tested >= 3 && point > 0 && Math.abs(bias) >= 0.03 * point
    ? ` Spending has tended to come in ${bias > 0 ? 'higher' : 'lower'} than forecast.`
    : ''
  return `${tested}${versus}.${lean}`
}

// Which method was used, and why.
export function describeMethod(data) {
  const n = data.candidates.length
  return n > 1 && data.accuracy && data.accuracy.months_tested >= 3
    ? `Method: ${data.model.label}. It was the most accurate of the ${n} methods tested on your own months.`
    : `Method: ${data.model.label}. There is too little history to compare methods yet.`
}

// What one-offs add on top, since they are left out of the number above.
export function describeOneOffs(data) {
  const o = data.one_offs
  if (Number(o.average_per_month) <= 0) return `No one-offs in the last ${o.window_months} months.`
  return `One-offs aren't in this number. They have averaged ${money(o.average_per_month)} a month (in ${o.months_with_one_offs} of the last ${o.window_months}), so a month with the usual one-offs would come to about ${money(o.with_one_offs)}.`
}

// One line per method tried, for the "how was this worked out" details.
export function describeCandidate(c) {
  const error = c.mape == null ? 'n/a' : `${c.mape}%`
  return `${c.label}: off by ${error} on average${c.chosen ? ' (used)' : ''}`
}

// Why the range is as wide as it is.
export function describeRange(data) {
  if (data.forecast.low == null) return ''
  return `The range is how far off this method has really been on your recent months, widened because that is only ${data.accuracy.months_tested} tests. About ${data.level}% of months should land inside it.`
}

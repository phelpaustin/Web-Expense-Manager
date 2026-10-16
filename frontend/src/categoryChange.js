// Presentation helpers for the "what changed vs last month" panel: the plain-English
// sentence and the waterfall chart's steps. Kept free of React so they are easy to test.
import { money } from './format.js'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// '2026-09' -> 'Sep'
export function monthShort(key) {
  return MONTHS[Number(key.slice(5, 7)) - 1] || key
}

// '2026-09' -> 'Sep 2026'
export function monthLabel(key) {
  return `${monthShort(key)} ${key.slice(0, 4)}`
}

// 1 -> '1st', 12 -> '12th', 23 -> '23rd'
export function ordinal(n) {
  const rem100 = n % 100
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`
  return `${n}${{ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th'}`
}

// '+SEK 800.00' / '-SEK 300.00' / 'SEK 0.00'
export function signedMoney(amount) {
  const n = Number(amount || 0)
  if (n === 0) return money(0)
  return `${n > 0 ? '+' : '-'}${money(Math.abs(n))}`
}

function joinList(parts) {
  if (parts.length <= 1) return parts.join('')
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

// The one-line answer to "why is spending different?", from the endpoint's response.
export function describeChange(data) {
  const { month, compare_month: before, partial, through_day: day, total } = data
  if (!data.available) return `No spending in ${monthLabel(before)} or ${monthLabel(month)} to compare.`

  const now = monthShort(month)
  const then = monthShort(before)
  const span = partial ? `${now} so far (to the ${ordinal(day)}) vs the same days of ${then}` : `${now} vs ${then}`
  const change = Number(total.change)

  if (Number(total.before) === 0) {
    const top = data.categories[0]
    return `${money(total.now)} spent in ${now}, with nothing in ${then} to compare with${top ? `, mostly ${top.category}` : ''}.`
  }
  if (change === 0) return `Spending is unchanged: ${span}.`

  const pct = total.pct_change == null ? '' : ` (${change > 0 ? '+' : ''}${total.pct_change}%)`
  const drivers = data.categories.map((c) => `${c.category} ${signedMoney(c.change)}`)
  if (data.other) {
    const n = data.other.count
    drivers.push(`${n} other${n === 1 ? '' : 's'} ${signedMoney(data.other.change)}`)
  }
  const lead = `Spending is ${change > 0 ? 'up' : 'down'} ${money(Math.abs(change))}${pct}: ${span}`
  return drivers.length ? `${lead}. Mostly ${joinList(drivers)}.` : `${lead}.`
}

// Steps for a waterfall: the earlier month's total, one floating bar per category that
// moved (rising or falling from where the last one ended), then the later month's total.
// `base` is the invisible part under a floating bar.
export function buildWaterfall(data) {
  const startName = monthShort(data.compare_month)
  const endName = data.partial ? `${monthShort(data.month)} so far` : monthShort(data.month)
  const steps = [{ name: startName, kind: 'total', base: 0, value: Number(data.total.before), amount: Number(data.total.before) }]
  let running = Number(data.total.before)

  const movers = [...data.categories.map((c) => ({ name: c.category, change: Number(c.change) }))]
  if (data.other) {
    const n = data.other.count
    movers.push({ name: `${n} other${n === 1 ? '' : 's'}`, change: Number(data.other.change) })
  }
  for (const m of movers) {
    const end = running + m.change
    steps.push({ name: m.name, kind: m.change >= 0 ? 'up' : 'down', base: Math.min(running, end), value: Math.abs(m.change), amount: m.change })
    running = end
  }
  steps.push({ name: endName, kind: 'total', base: 0, value: Number(data.total.now), amount: Number(data.total.now) })
  return steps
}

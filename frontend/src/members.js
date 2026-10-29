// Presentation helpers for "spending by member". No React, so they are easy to test.
import { money } from './format.js'

export const PERIODS = [
  { key: 'this_month', label: 'This month' },
  { key: 'last_month', label: 'Last month' },
  { key: 'last_90', label: 'Last 90 days' },
  { key: 'this_year', label: 'This year' },
  { key: 'all', label: 'All time' },
]
export const DEFAULT_PERIOD = 'this_month'

const pad = (n) => String(n).padStart(2, '0')
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// { dateFrom, dateTo } (YYYY-MM-DD, in the person's own calendar) for a period key; undefined ends mean "no limit".
export function periodRange(key, now = new Date()) {
  const y = now.getFullYear()
  const m = now.getMonth()
  switch (key) {
    case 'this_month':
      return { dateFrom: iso(new Date(y, m, 1)), dateTo: iso(now) }
    case 'last_month':
      return { dateFrom: iso(new Date(y, m - 1, 1)), dateTo: iso(new Date(y, m, 0)) }
    case 'last_90':
      return { dateFrom: iso(new Date(y, m, now.getDate() - 89)), dateTo: iso(now) }
    case 'this_year':
      return { dateFrom: `${y}-01-01`, dateTo: iso(now) }
    default:
      return { dateFrom: undefined, dateTo: undefined }
  }
}

export function periodLabel(key) {
  return (PERIODS.find((p) => p.key === key) || PERIODS[0]).label
}

// What to call a member: their name, else their email, with "(you)" for the person looking.
export function memberLabel(m) {
  const base = m.name || m.email || (m.user_id == null ? 'Unknown' : 'Member')
  return m.is_me ? `${base} (you)` : base
}

const PALETTE = ['#6d7bff', '#10b981', '#f59e0b', '#ef4444', '#a674ff', '#06b6d4', '#ec4899', '#84cc16']
export const OTHER_COLOR = '#9aa3b8'

// One colour per member, in member-id order, so a member keeps their colour when the ranking changes.
export function memberColors(members) {
  const ids = members.map((m) => m.user_id).sort((a, b) => (a == null) - (b == null) || a - b)
  const out = new Map()
  ids.forEach((id, i) => out.set(id, i < PALETTE.length ? PALETTE[i] : OTHER_COLOR))
  return out
}

// One row per member for the bar chart.
export function memberBars(data, colors = memberColors(data.members)) {
  return data.members.map((m) => ({ id: m.user_id, name: memberLabel(m), total: Number(m.total), share_pct: m.share_pct, count: m.count, color: colors.get(m.user_id) }))
}

// One row per month for the stacked chart: { month, name, total, m<id>: amount }.
export function trendRows(data) {
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return data.months.map((mo) => {
    const row = { month: mo.month, name: `${names[Number(mo.month.slice(5, 7)) - 1]} ${mo.month.slice(2, 4)}`, total: Number(mo.total) }
    for (const b of mo.by_member) row[`m${b.user_id}`] = Number(b.total)
    return row
  })
}

// "Ann (you) 80% · Bob 20%", biggest first.
export function sharesText(data) {
  return data.members
    .filter((m) => m.count > 0)
    .map((m) => `${memberLabel(m)} ${m.share_pct}%`)
    .join(' · ')
}

// "Across Home and Goa Trip".
export function spacesText(spaces) {
  const names = spaces.map((s) => s.name)
  if (names.length <= 1) return names.length ? `In ${names[0]}` : ''
  return `Across ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

// A sentence on the whole answer, or why there is nothing to say.
export function summaryText(data) {
  if (!data.spaces.length) return 'Spending by member needs a shared space with other people in it.'
  if (!data.count) return 'Nothing was spent in the shared spaces in this period.'
  const top = data.members[0]
  const lead = data.members.length > 1 && top.count > 0 ? ` ${memberLabel(top)} paid the most: ${top.share_pct}%.` : ''
  return `${money(data.total)} was spent in ${data.count} ${data.count === 1 ? 'expense' : 'expenses'}.${lead}`
}

export function describeBars(rows) {
  return `Bar chart of spending by member: ${rows.map((r) => `${r.name} ${money(r.total)}`).join(', ')}.`
}

// The amount a member spent in one row of the category table.
export function cellAmount(category, userId) {
  const found = category.by_member.find((b) => b.user_id === userId)
  return found ? Number(found.total) : 0
}

export function topCategoriesText(m) {
  return m.top_categories.map((c) => `${c.category} ${money(c.total)}`).join(', ')
}

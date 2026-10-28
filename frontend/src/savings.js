// Presentation helpers for the Savings page. No React, so they are easy to test.
import { money } from './format.js'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "2027-03-05" -> "5 Mar 2027". Read from the text, never through a Date, so no time zone can move the day.
export function formatDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '')
  if (!m) return ''
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`
}

// Today in the person's own calendar, as YYYY-MM-DD (toISOString would give the UTC day).
export function todayLocal(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export const STATUS = {
  reached: { label: 'Reached', tone: 'good' },
  on_track: { label: 'On track', tone: 'good' },
  behind: { label: 'Behind', tone: 'bad' },
  overdue: { label: 'Overdue', tone: 'bad' },
  no_deadline: { label: 'No deadline', tone: 'neutral' },
}

export function statusInfo(status) {
  return STATUS[status] || STATUS.no_deadline
}

// The bar never goes past full, and any progress at all stays visible.
export function barPercent(goal) {
  const pct = Number(goal.pct)
  if (!(pct > 0)) return 0
  return Math.min(100, Math.max(1, Math.round(pct)))
}

// "SEK 3,000.00 of SEK 10,000.00"
export function savedText(goal) {
  return `${money(goal.saved, goal.currency)} of ${money(goal.target_amount, goal.currency)}`
}

// One or two sentences on where the goal stands and what it needs.
export function paceText(goal) {
  const c = goal.currency
  const pace = Number(goal.recent_per_month)
  const target = formatDate(goal.target_date)
  switch (goal.status) {
    case 'reached':
      return 'You’ve reached this goal.'
    case 'overdue':
      return `The target date (${target}) has passed with ${money(goal.remaining, c)} still to go.`
    case 'on_track':
      return `At your recent pace of ${money(goal.recent_per_month, c)} a month you’d get there around ${formatDate(goal.projected_date)}, in time for ${target}.`
    case 'behind':
      return pace > 0
        ? `To reach it by ${target} you need ${money(goal.needed_per_month, c)} a month. You’re saving ${money(goal.recent_per_month, c)} a month, ${money(goal.shortfall_per_month, c)} short.`
        : `To reach it by ${target} you need ${money(goal.needed_per_month, c)} a month, and nothing has been added in the last 90 days.`
    default:
      return goal.projected_date
        ? `At your recent pace of ${money(goal.recent_per_month, c)} a month you’d get there around ${formatDate(goal.projected_date)}.`
        : 'No target date. Add money and you’ll see when you’d get there.'
  }
}

// "12 days left", "Due today", "Passed 3 days ago", or '' with no date.
export function daysLeftText(goal) {
  const n = goal.days_left
  if (n == null || goal.status === 'reached') return ''
  if (n === 0) return 'Due today'
  if (n < 0) return `Passed ${-n} ${-n === 1 ? 'day' : 'days'} ago`
  return `${n} ${n === 1 ? 'day' : 'days'} left`
}

export function summaryText(summary) {
  if (!summary || !summary.goals) return ''
  const parts = [`${summary.goals} ${summary.goals === 1 ? 'goal' : 'goals'}`]
  if (summary.reached) parts.push(`${summary.reached} reached`)
  if (summary.behind) parts.push(`${summary.behind} behind`)
  return parts.join(' · ')
}

export function contributionText(c, currency) {
  const amount = Number(c.amount)
  return `${amount < 0 ? 'Withdrew' : 'Added'} ${money(Math.abs(amount), currency)} on ${formatDate(c.date)}${c.note ? `: ${c.note}` : ''}`
}

// What to send for the add-money form. Returns { error } or { body }.
export function contributionBody({ kind, amount, date, note }) {
  const n = Number(amount)
  if (!(n > 0)) return { error: 'Enter an amount above zero.' }
  if (Math.round(n * 100) === 0) return { error: 'Enter at least 0.01.' }
  const body = { amount: `${kind === 'withdraw' ? '-' : ''}${String(amount).trim()}`, note: (note || '').trim() }
  if (date) body.date = date
  return { body }
}

// What to send for the new-goal and edit forms. Returns { error } or { body }.
export function goalBody({ name, target, currency, targetDate, note }, { includeCurrency = true } = {}) {
  const cleanName = (name || '').trim()
  if (!cleanName) return { error: 'Give the goal a name.' }
  const n = Number(target)
  if (!(n > 0)) return { error: 'The target must be above zero.' }
  const body = { name: cleanName, target_amount: String(target).trim(), target_date: targetDate || null, note: (note || '').trim() }
  if (includeCurrency && currency) body.currency = currency
  return { body }
}

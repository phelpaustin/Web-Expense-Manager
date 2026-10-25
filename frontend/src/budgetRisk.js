// Presentation helpers for the "chance of going over" panel, kept free of React so they are easy to test.
import { money } from './format.js'
import { ordinal } from './categoryChange.js'

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export const RISK_COLORS = {
  over: '#dc2626',
  very_likely: '#f97316',
  likely: '#f59e0b',
  possible: '#eab308',
  unlikely: '#10b981',
}

const LEVEL_LABELS = {
  over: 'Already over',
  very_likely: 'Very likely',
  likely: 'Likely',
  possible: 'Possible',
  unlikely: 'Unlikely',
}

export function levelLabel(level) {
  return LEVEL_LABELS[level] || 'Not estimated'
}

// 'month' or 'week': what one sample is.
export function periodUnit(item) {
  return item.align === 'week' ? 'week' : 'month'
}

// "the 21st" (of the month) or "Wednesday" (of the week): the point the earlier periods are compared from.
export function sinceLabel(item) {
  return item.align === 'week' ? WEEKDAYS[item.anchor] : `the ${ordinal(item.anchor)}`
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

// The chance, as a whole percent.
export function percent(item) {
  return `${Math.round(item.probability)}%`
}

// Why the chance is what it is, in a sentence or two.
export function describeRisk(item, minPeriods = 4) {
  if (item.level === 'over') return `Over budget by ${money(-Number(item.remaining))}.`
  if (!item.available) {
    return `Needs ${minPeriods} earlier ${periodUnit(item)}s of history to estimate this (${item.samples} so far).`
  }
  if (item.days_remaining <= 0) return `The ${periodUnit(item)} ends today and you are within budget.`
  const unit = periodUnit(item)
  const left = `${money(item.remaining)} left with ${plural(item.days_remaining, 'day')} to go.`
  const evidence = `In ${item.exceeded} of the last ${plural(item.samples, unit)}, spending after ${sinceLabel(item)} went past that.`
  const typical = Number(item.typical_remaining) > 0 ? ` Typically about ${money(item.typical_remaining)} more is spent.` : ''
  return `${left} ${evidence}${typical}`
}

// One line for the top of the panel.
export function headline(risk) {
  const estimated = risk.items.filter((i) => i.available)
  if (estimated.length === 0) return 'Not enough history yet to estimate the chance of going over.'
  const over = estimated.filter((i) => i.level === 'over').length
  const likely = estimated.filter((i) => i.level !== 'over' && i.probability >= risk.alert_threshold).length
  const parts = []
  if (over) parts.push(`${plural(over, 'budget')} already over`)
  if (likely) parts.push(`${plural(likely, 'budget')} very likely to be exceeded`)
  return parts.length ? `${parts.join(', ')}.` : 'No budget looks likely to be exceeded.'
}

// What the percentages are based on.
export function describeMethod(risk) {
  return `Based on what was spent over the same stretch of earlier months or weeks: how often it was more than the room you have left now. It needs ${risk.min_periods} earlier periods, and it is never 0% or 100% unless the outcome is already settled, since a few past periods can't prove either. You are warned when the chance reaches ${risk.alert_threshold}%.`
}

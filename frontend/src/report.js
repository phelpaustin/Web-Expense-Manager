// Presentation helpers for the yearly / monthly report. No React, so they are easy to test.
import { money } from './format.js'

export const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
export const CHART_CATEGORIES = 12

// The years to offer: the ones with data plus the selected one, newest first.
export function yearChoices(years, selected) {
  return [...new Set([...(Array.isArray(years) ? years : []), selected])].filter((y) => Number.isInteger(y)).sort((a, b) => b - a)
}

// "▲ 12.5% vs 2025 (SEK 200.00)", or why there is nothing to compare with.
export function changeText(data) {
  const p = data.previous
  if (!p || !(Number(p.spent) > 0)) return `Nothing recorded in ${p ? p.label : 'the period before'} to compare with.`
  const pct = p.change_pct
  const arrow = Number(p.change) >= 0 ? '▲' : '▼'
  return `${arrow} ${Math.abs(pct)}% vs ${p.label} (${money(p.spent)})`
}

export function changeDirection(data) {
  return data.previous && Number(data.previous.change) >= 0 ? 'up' : 'down'
}

// One or two sentences on the whole report.
export function summaryText(data) {
  const t = data.totals
  if (!t.count) return `No spending recorded in ${data.label}.`
  const parts = [`You spent ${money(t.spent)} in ${data.label} across ${t.count} ${t.count === 1 ? 'expense' : 'expenses'}.`]
  const top = data.categories[0]
  if (top && data.categories.length > 1) parts.push(`${top.category} was the biggest category at ${top.share_pct}%.`)
  if (data.peak) parts.push(`The highest ${data.kind === 'month' ? 'day' : 'month'} was ${data.peak.label} (${money(data.peak.total)}).`)
  return parts.join(' ')
}

// The categories to draw: the biggest few, and everything else as one "Other" bar.
export function chartCategories(categories, limit = CHART_CATEGORIES) {
  const shown = categories.slice(0, limit).map((c) => ({ name: c.category, total: Number(c.total), share_pct: c.share_pct, count: c.count }))
  const rest = categories.slice(limit)
  if (rest.length) {
    shown.push({
      name: `Other (${rest.length})`,
      total: rest.reduce((sum, c) => sum + Number(c.total), 0),
      share_pct: Math.round(rest.reduce((sum, c) => sum + c.share_pct, 0) * 10) / 10,
      count: rest.reduce((sum, c) => sum + c.count, 0),
      other: true,
    })
  }
  return shown
}

export function categoryChartHeight(rows) {
  return Math.max(120, rows.length * 30 + 20)
}

export function describeCategoryChart(rows) {
  return `Bar chart of spending by category: ${rows.map((r) => `${r.name} ${money(r.total)}`).join(', ')}.`
}

export function periodChartRows(periods) {
  return periods.map((p) => ({ key: p.key, name: p.label, total: Number(p.total), count: p.count }))
}

export function describePeriodChart(data) {
  const unit = data.kind === 'month' ? 'day' : 'month'
  const peak = data.peak ? ` Highest ${unit}: ${data.peak.label}, ${money(data.peak.total)}.` : ''
  return `Bar chart of spending by ${unit}.${peak}`
}

// Axis labels: months shrink to their first letter on a phone, where twelve names would run together.
export function tickLabel(label, daily, phone) {
  return phone && !daily ? String(label).charAt(0) : label
}

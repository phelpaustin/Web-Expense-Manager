// Presentation helpers for the "Price rises" panel. No React, so they are easy to test.
import { money } from './format.js'

export const WINDOWS = [
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'Last 90 days' },
]

export function windowLabel(days) {
  return (WINDOWS.find((w) => w.days === days) || { label: `Last ${days} days` }).label
}

// "Milk (Arla)" when the brand is part of what is followed.
export function riseName(i) {
  return i.brand ? `${i.item} (${i.brand})` : i.item
}

// One sentence per rise, also its readable summary.
export function describeRise(i) {
  return `${riseName(i)} at ${i.shop} now costs ${money(i.latest_price)} per ${i.unit}, ${i.rise_pct}% more than your usual ${money(i.usual_price)}.`
}

// 25% and over is a warning, as in the bell.
export function isBigRise(i) {
  return i.rise_pct >= 25
}

// What to say under the table, or instead of it.
export function summaryText(data) {
  const days = data.recent_days
  if (data.items.length === 0) {
    if (data.checked === 0) {
      return `Nothing to compare yet: no item bought in the last ${days} days has at least 2 earlier purchases at the same shop.`
    }
    return `No price rises in the last ${days} days: ${data.checked} ${data.checked === 1 ? 'item' : 'items'} checked, none up ${data.min_rise_pct}% or more.`
  }
  return ''
}

// Presentation helpers for the "Cheapest shop per item" panel. No React, so they are easy to test.
import { money } from './format.js'

export const LOOKBACKS = [
  { months: 3, label: 'Last 3 months' },
  { months: 6, label: 'Last 6 months' },
  { months: 12, label: 'Last 12 months' },
  { months: 24, label: 'Last 2 years' },
  { months: 0, label: 'All time' },
]

export function lookbackLabel(months) {
  return (LOOKBACKS.find((l) => l.months === months) || { label: `Last ${months} months` }).label
}

// 'once' / '3 times'
export function timesText(n) {
  return n === 1 ? 'once' : `${n} times`
}

// The item as it is shown: "Milk (Arla)" when the brand is part of what is compared.
export function itemName(i) {
  return i.brand ? `${i.item} (${i.brand})` : i.item
}

// One sentence for an item, also its readable summary.
export function describeSaving(i) {
  return `${itemName(i)}: ${i.cheapest.shop} averages ${money(i.cheapest.avg_price)} per ${i.unit}, ${i.saving_pct}% less than ${i.usual.shop} (${money(i.usual.avg_price)}), where you usually buy it.`
}

// What to say under the table, or instead of it.
export function summaryText(data) {
  if (data.compared === 0) return 'No item has been bought at more than one shop in this period yet.'
  if (data.items.length === 0) {
    return `For the ${data.compared} ${data.compared === 1 ? 'item' : 'items'} you bought at more than one shop, your usual shop is already about as cheap as any.`
  }
  if (data.already_cheapest > 0) {
    return `For ${data.already_cheapest} other ${data.already_cheapest === 1 ? 'item' : 'items'} your usual shop is already the cheapest.`
  }
  return ''
}

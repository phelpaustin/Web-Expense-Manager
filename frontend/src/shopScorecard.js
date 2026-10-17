// Presentation helpers for the Shops page, kept free of React so they are easy to test.
import { money } from './format.js'

export const PERIODS = [
  { months: 1, label: 'Last month' },
  { months: 3, label: 'Last 3 months' },
  { months: 6, label: 'Last 6 months' },
  { months: 12, label: 'Last 12 months' },
  { months: 0, label: 'All time' },
]
export const DEFAULT_MONTHS = 6

// How one shop's prices compare with the other shops for the same things.
// `tone` picks the colour: 'good' (cheaper), 'bad' (dearer), or plain text otherwise.
export function priceLevel(shop, minItems) {
  if (shop.price_index != null) {
    const gap = Math.round(Math.abs(shop.price_index - 100))
    if (gap === 0) return { text: 'About average', tone: 'neutral' }
    return shop.price_index < 100 ? { text: `${gap}% cheaper`, tone: 'good' } : { text: `${gap}% dearer`, tone: 'bad' }
  }
  if (shop.items_compared === 0) return { text: '—', tone: 'none', hint: 'Nothing here is also bought at another shop' }
  return {
    text: '—',
    tone: 'none',
    hint: `Needs ${minItems} items bought at other shops too (${shop.items_compared} so far)`,
  }
}

// One "where you could save" line.
export function describeOpportunity(o) {
  const name = o.brand ? `${o.item} (${o.brand})` : o.item
  const more = o.pay_more_pct == null ? '' : `, ${o.pay_more_pct}% more`
  return `${name}: ${money(o.price)}/${o.unit} at ${o.shop} vs ${money(o.cheaper_price)}/${o.unit} at ${o.cheaper_shop}${more}. About ${money(o.saving)} over this period.`
}

// "3 of 5" for how many shared items a shop is cheapest on; a dash when none are shared.
export function cheapestOn(shop) {
  return shop.items_compared > 0 ? `${shop.cheapest_on} of ${shop.items_compared}` : '—'
}

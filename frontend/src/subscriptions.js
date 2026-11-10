// Presentation helpers for the subscription finder. No React, so they are easy to test.
import { money } from './format.js'

export { dayLabel, perText, priceChangeText } from './recurringCosts.js'

// "3 repeating charges you haven't set up cost about SEK 640.00 a month (SEK 7,680.00 a year)."
export function headline(data) {
  const n = data.count
  if (n === 0) {
    return data.tracked_count > 0
      ? 'No other repeating charges found: the ones found are already in your recurring payments.'
      : 'No repeating charges found yet. They show up once the same shop charges you at a steady rhythm a few times.'
  }
  const noun = n === 1 ? 'repeating charge you haven’t set up costs' : 'repeating charges you haven’t set up cost'
  return `${n} ${noun} about ${money(data.monthly_total, data.currency)} a month (${money(data.yearly_total, data.currency)} a year).`
}

// The recurring payment to create from a found subscription. last_applied is the charge already
// made, so the schedule starts after it and nothing is posted twice.
export function trackPayload(item) {
  return {
    item: item.name,
    category: item.category || '',
    amount: String(item.amount),
    frequency: item.frequency,
    currency: item.currency,
    last_applied: item.last_date,
    auto_post: false,
  }
}

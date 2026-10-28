// Club same-day, same-shop rows into one "bill": that is how a single receipt is entered, whether one
// item at a time or in bill mode. Rows without a shop aren't grouped; nothing ties them to a receipt.
// Shared by the Spending page and the month detail window so both group the same way.
export function groupIntoBills(expenses) {
  const groups = []
  const indexByKey = new Map()
  for (const e of expenses) {
    const shop = (e.shop || '').trim()
    const key = shop
      ? `${e.date}::${shop}::${e.group_id ?? 'personal'}::${e.currency || 'SEK'}`
      : `single-${e.id}`
    let group = indexByKey.get(key)
    if (!group) {
      group = { key, date: e.date, shop, group_id: e.group_id, currency: e.currency || 'SEK', items: [] }
      indexByKey.set(key, group)
      groups.push(group)
    }
    group.items.push(e)
  }
  return groups
}

// One line's worth of a bill: its total (every item shares a currency, by the grouping key), summed in
// whole cents so amounts never pick up float noise.
export function billTotal(items) {
  const cents = items.reduce((sum, e) => sum + Math.round(Number(e.amount || 0) * 100), 0)
  return { currency: items[0].currency || 'SEK', total: cents / 100 }
}

// "Meat" when every item is in one category, otherwise "3 categories".
export function categorySummary(items) {
  const categories = new Set(items.map((e) => e.category || 'Uncategorized'))
  return categories.size === 1 ? [...categories][0] : `${categories.size} categories`
}

import { describe, it, expect } from 'vitest'
import { groupIntoBills, billTotal, categorySummary } from '../billGroups.js'

const e = (id, over = {}) => ({ id, date: '2026-09-24', shop: 'Lidl', currency: 'SEK', group_id: null, category: 'Food', amount: '10', ...over })

describe('groupIntoBills', () => {
  it('clubs same-day, same-shop, same-space, same-currency rows in the order first seen', () => {
    const groups = groupIntoBills([e(1), e(2, { shop: 'ICA' }), e(3)])
    expect(groups.map((g) => g.items.map((i) => i.id))).toEqual([[1, 3], [2]])
    expect(groups[0]).toMatchObject({ date: '2026-09-24', shop: 'Lidl', currency: 'SEK' })
  })

  it('keeps different days, spaces and currencies apart', () => {
    const groups = groupIntoBills([e(1), e(2, { date: '2026-09-25' }), e(3, { group_id: 4 }), e(4, { currency: 'EUR' })])
    expect(groups).toHaveLength(4)
  })

  it('never groups rows without a shop, and ignores stray spaces around a shop name', () => {
    expect(groupIntoBills([e(1, { shop: '' }), e(2, { shop: '  ' }), e(3, { shop: null })])).toHaveLength(3)
    expect(groupIntoBills([e(1, { shop: 'Lidl ' }), e(2)])).toHaveLength(1)
  })
})

describe('billTotal', () => {
  it('adds in whole cents so there is no float noise', () => {
    expect(billTotal([e(1, { amount: '0.1' }), e(2, { amount: '0.2' })])).toEqual({ currency: 'SEK', total: 0.3 })
  })
})

describe('categorySummary', () => {
  it('names the one category, or counts several', () => {
    expect(categorySummary([e(1), e(2)])).toBe('Food')
    expect(categorySummary([e(1), e(2, { category: 'Meat' })])).toBe('2 categories')
    expect(categorySummary([e(1, { category: '' })])).toBe('Uncategorized')
  })
})

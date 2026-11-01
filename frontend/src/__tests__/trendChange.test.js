import { describe, it, expect } from 'vitest'
import { describeChange } from '../components/TrendMeta.jsx'

describe('describeChange', () => {
  it('shows size and direction for a rise and a fall', () => {
    expect(describeChange({ direction: 'up', pct_change: 12.5 })).toEqual({ arrow: '▲', text: '12.5%', className: 'up' })
    expect(describeChange({ direction: 'down', pct_change: -8 })).toEqual({ arrow: '▼', text: '8%', className: 'down' })
  })

  it('says so when there was no spend before, instead of printing 0%', () => {
    expect(describeChange({ direction: 'up', pct_change: null }).text).toBe('n/a (no spend before)')
  })

  it('does not colour a flat month as a fall', () => {
    expect(describeChange({ direction: 'flat', pct_change: 0 })).toEqual({ arrow: '■', text: '0%', className: '' })
  })
})

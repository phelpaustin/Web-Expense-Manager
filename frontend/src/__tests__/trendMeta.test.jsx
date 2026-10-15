import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TrendMeta from '../components/TrendMeta.jsx'

const base = { current_month: '2026-10', forecast_next_month: null, change: null }

describe('TrendMeta', () => {
  it('labels the compared finished months and notes the partial month', () => {
    render(
      <TrendMeta
        trends={{ ...base, change: { last_month: '2026-09', previous_month: '2026-08', pct_change: 2, direction: 'up' } }}
      />,
    )
    expect(screen.getByText(/Sep vs Aug/)).toBeTruthy()
    expect(screen.getByText(/2%/)).toBeTruthy()
    expect(screen.getByText(/Oct is still in progress/)).toBeTruthy()
  })

  it('shows n/a instead of a percentage when the earlier month had no spend', () => {
    render(
      <TrendMeta
        trends={{ ...base, change: { last_month: '2026-09', previous_month: '2026-08', pct_change: null, direction: 'up' } }}
      />,
    )
    expect(screen.getByText(/n\/a/)).toBeTruthy()
  })

  it('shows the forecast for the current month and hides it when absent', () => {
    const { rerender } = render(<TrendMeta trends={{ ...base, forecast_next_month: 4200 }} />)
    expect(screen.getByText(/forecast for Oct/)).toBeTruthy()
    rerender(<TrendMeta trends={base} />)
    expect(screen.queryByText(/forecast for/)).toBeNull()
  })
})

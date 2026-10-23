import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TrendMeta from '../components/TrendMeta.jsx'

const base = { current_month: '2026-10', change: null }

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

  it('no longer shows a forecast: that has its own panel with a range and a track record', () => {
    render(<TrendMeta trends={{ ...base, forecast_next_month: 4200 }} />)
    expect(screen.queryByText(/forecast/i)).toBeNull()
  })

  it('says the month in progress is left out of the change', () => {
    render(
      <TrendMeta
        trends={{ ...base, change: { last_month: '2026-09', previous_month: '2026-08', pct_change: 2, direction: 'up' } }}
      />,
    )
    expect(screen.getByText(/Oct is still in progress, so it is left out of the change\./)).toBeTruthy()
  })
})

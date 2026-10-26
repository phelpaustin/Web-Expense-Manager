import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, fireEvent, act } from '@testing-library/react'
import { cloneElement } from 'react'

// jsdom has no layout, so give the charts a fixed size instead of measuring a container.
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ResponsiveContainer: ({ children, height }) => cloneElement(children, { width: 600, height }),
  }
})

vi.mock('../api/client.js', () => ({ fetchSpendingMix: vi.fn() }))

import { render as renderMix, screen } from '@testing-library/react'
import { fetchSpendingMix } from '../api/client.js'
import SpendingMixPanel from '../components/SpendingMixPanel.jsx'
import { SpendingTrendChart, CashFlowChart } from '../components/Charts.jsx'

const TREND = [
  { month: '2025-01', total: 100 },
  { month: '2025-02', total: 200 },
  { month: '2025-03', total: 300 },
]
const FLOW = TREND.map((t) => ({ month: t.month, income: 500, expenses: t.total }))

// Recharts maps a click to a month using the element's measured size, which jsdom reports as 0.
beforeAll(() => {
  const size = { width: 600, height: 260 }
  const isChart = (el) => el.classList?.contains('recharts-wrapper')
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
    configurable: true, get() { return isChart(this) ? size.width : 0 },
  })
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true, get() { return isChart(this) ? size.height : 0 },
  })
  // Only the chart wrapper has a size; the legend and axes measure as empty, as they do in jsdom.
  Element.prototype.getBoundingClientRect = function rect() {
    const { width, height } = isChart(this) ? size : { width: 0, height: 0 }
    return { x: 0, y: 0, left: 0, top: 0, right: width, bottom: height, width, height, toJSON() {} }
  }
})

// Recharts handles mouse moves on the next animation frame, so let the hover settle before clicking.
async function clickAt(container, x) {
  const surface = container.querySelector('.recharts-wrapper')
  fireEvent.mouseMove(surface, { clientX: x, clientY: 100 })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
  fireEvent.click(surface, { clientX: x, clientY: 100 })
}

describe('clicking a month on a chart', () => {
  it('reports the month on the spending trend', async () => {
    const onSelect = vi.fn()
    const { container } = render(<SpendingTrendChart data={TREND} onSelectMonth={onSelect} />)
    await clickAt(container, 570)
    expect(onSelect).toHaveBeenCalledWith('2025-03')
  })

  it('reports the month on cash flow', async () => {
    const onSelect = vi.fn()
    const { container } = render(<CashFlowChart data={FLOW} onSelectMonth={onSelect} />)
    await clickAt(container, 100)
    expect(onSelect).toHaveBeenCalledWith('2025-01')
  })

  it('does nothing without a handler', async () => {
    const { container } = render(<SpendingTrendChart data={TREND} />)
    await expect(clickAt(container, 300)).resolves.not.toThrow()
  })

  it('reports the month on the committed vs everyday chart', async () => {
    fetchSpendingMix.mockResolvedValue({
      window: { from: '2025-11-01', to: '2026-01-31', months: 3 }, available: true, currency: 'SEK', unconverted_count: 0,
      months: ['2025-11', '2025-12', '2026-01'].map((month) => ({ month, committed: 1, everyday: 2, one_off: 0, total: 3, partial: false })),
      typical: null, totals: { committed: 3, everyday: 6, one_off: 0, total: 9, committed_pct: 33.3, one_off_pct: 0 },
      one_off_count: 0, one_offs: [], committed_top: [], rule: { min_samples: 8, multiple: 3, sigmas: 3 },
    })
    const onSelect = vi.fn()
    const { container } = renderMix(<SpendingMixPanel scope="all" spaceIds={[]} refreshKey={0} onSelectMonth={onSelect} />)
    await screen.findByTestId('mix-chart')
    await clickAt(container, 100)
    expect(onSelect).toHaveBeenCalledWith('2025-11')
  })
})

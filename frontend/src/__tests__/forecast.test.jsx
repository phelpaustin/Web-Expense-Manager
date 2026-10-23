import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})
// Recharts measures real layout, which jsdom doesn't have; the chart's data is tested directly.
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>
  const None = () => null
  return { BarChart: Pass, Bar: Pass, ErrorBar: None, CartesianGrid: None, XAxis: None, YAxis: None, Tooltip: None, ResponsiveContainer: Pass }
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import {
  chartRows, describeForecast, describeSoFar, describeAccuracy, describeMethod, describeOneOffs, describeCandidate, describeRange,
} from '../forecast.js'
import ForecastPanel from '../components/ForecastPanel.jsx'

beforeAll(() => setDisplayCurrency('USD')) // dollars keep the expected text short

const REQ = { min_months: 3, months_to_test: 5, months_for_range: 7, months_for_seasons: 27 }

const DATA = {
  available: true, reason: null, month: '2026-10', requirements: REQ, level: 80, months_available: 9, skipped_first_month: false,
  forecast: { point: 11865, low: 11000, high: 12730 },
  model: { name: 'mean3', label: 'Average of the last 3 months', seasonal_considered: false },
  accuracy: { months_tested: 5, mape: 8.7, mae: 900, bias: 50, naive_mape: 14.1, beats_naive: true },
  candidates: [
    { name: 'naive', label: 'Same as last month', mape: 14.1, rmse: 1500, chosen: false },
    { name: 'mean3', label: 'Average of the last 3 months', mape: 8.7, rmse: 1000, chosen: true },
  ],
  so_far: { day: 21, total: 9750, baseline: 9750, one_off: 0 },
  one_offs: { average_per_month: 722.22, months_with_one_offs: 1, window_months: 9, with_one_offs: 12587.22 },
  history: [
    { month: '2026-08', baseline: 11800, one_off: 0, total: 11800 },
    { month: '2026-09', baseline: 11900, one_off: 6500, total: 18400 },
  ],
  categories: [
    { category: 'Housing', forecast: 9000, last_month: 9000, change: 0, share_pct: 75.9, rollup: false },
    { category: 'Groceries', forecast: 2865, last_month: 2900, change: -35, share_pct: 24.1, rollup: false },
  ],
  currency: 'SEK', unconverted_count: 0,
}

describe('chartRows', () => {
  it('draws each recent month as baseline with its one-offs on top, then the forecast with its range', () => {
    expect(chartRows(DATA)).toEqual([
      { name: 'Aug', month: '2026-08', baseline: 11800, oneOff: 0, forecast: 0, isForecast: false },
      { name: 'Sep', month: '2026-09', baseline: 11900, oneOff: 6500, forecast: 0, isForecast: false },
      { name: 'Oct*', month: '2026-10', baseline: 0, oneOff: 0, forecast: 11865, error: [865, 865], isForecast: true },
    ])
  })

  it('has no whisker when there is no range yet', () => {
    const rows = chartRows({ ...DATA, forecast: { point: 600, low: null, high: null } })
    expect(rows.at(-1).error).toBeUndefined()
  })

  it('accepts numbers sent as text', () => {
    const rows = chartRows({ ...DATA, history: [{ month: '2026-08', baseline: '10.5', one_off: '2', total: '12.5' }], forecast: { point: '20', low: '15', high: '26' } })
    expect(rows[0]).toMatchObject({ baseline: 10.5, oneOff: 2 })
    expect(rows[1]).toMatchObject({ forecast: 20, error: [5, 6] })
  })
})

describe('sentences', () => {
  it('gives the number and the range, without one-offs', () => {
    expect(describeForecast(DATA)).toBe('Oct 2026 is on track for about $11,865.00, most likely between $11,000.00 and $12,730.00 (not counting one-offs).')
  })

  it('says what a range needs when there is only a number', () => {
    expect(describeForecast({ ...DATA, forecast: { point: 600, low: null, high: null }, months_available: 4 })).toBe(
      'Oct 2026 is on track for about $600.00 (not counting one-offs). A range needs 7 finished months; you have 4.',
    )
  })

  it('explains why there is no forecast', () => {
    expect(describeForecast({ ...DATA, available: false, reason: 'no_spending' })).toBe('No spending recorded yet.')
    expect(describeForecast({ ...DATA, available: false, reason: 'not_enough_history', months_available: 2 })).toBe(
      'A forecast needs at least 3 finished months of spending; you have 2.',
    )
  })

  it('copes with a response that has no details rather than breaking the page', () => {
    expect(describeForecast({})).toBe('A forecast needs at least 3 finished months of spending; you have 0.')
    expect(describeForecast({ available: false, reason: 'no_spending' })).toBe('No spending recorded yet.')
  })

  it('reports spending so far, with any one-offs in it', () => {
    expect(describeSoFar(DATA)).toBe('So far this month (to the 21st): $9,750.00.')
    expect(describeSoFar({ ...DATA, so_far: { day: 2, total: 4100, baseline: 100, one_off: 4000 } })).toBe(
      'So far this month (to the 2nd): $4,100.00, including $4,000.00 of one-offs.',
    )
  })

  it('reports the track record against simply repeating last month', () => {
    expect(describeAccuracy(DATA)).toBe(
      "Tested on your last 5 months, this method was off by 8.7% on average (assuming last month's spending again would have been off by 14.1%).",
    )
  })

  it('leaves out the comparison when the method is last month itself', () => {
    expect(describeAccuracy({ ...DATA, accuracy: { ...DATA.accuracy, beats_naive: null } })).not.toMatch(/assuming last month/)
  })

  it('says when spending has tended to come in higher or lower than forecast', () => {
    const high = describeAccuracy({ ...DATA, accuracy: { ...DATA.accuracy, bias: 600 } })
    const low = describeAccuracy({ ...DATA, accuracy: { ...DATA.accuracy, bias: -600 } })
    expect(high).toMatch(/tended to come in higher than forecast\.$/)
    expect(low).toMatch(/tended to come in lower than forecast\.$/)
    expect(describeAccuracy(DATA)).not.toMatch(/tended/)                                          // a small bias is not worth saying
    expect(describeAccuracy({ ...DATA, accuracy: { ...DATA.accuracy, months_tested: 2, bias: 600 } })).not.toMatch(/tended/) // two tests prove nothing
  })

  it('explains an untested method and a single test', () => {
    expect(describeAccuracy({ ...DATA, accuracy: null })).toBe('Not enough history to test the method yet (it needs 5 finished months).')
    expect(describeAccuracy({ ...DATA, accuracy: { ...DATA.accuracy, months_tested: 1 } })).toMatch(/Tested on your last 1 month,/)
  })

  it('says which method was used, and why or why not it was compared', () => {
    expect(describeMethod(DATA)).toBe('Method: Average of the last 3 months. It was the most accurate of the 2 methods tested on your own months.')
    expect(describeMethod({ ...DATA, candidates: [], accuracy: null })).toBe('Method: Average of the last 3 months. There is too little history to compare methods yet.')
  })

  it('says what one-offs add on top, or that there were none', () => {
    expect(describeOneOffs(DATA)).toBe(
      "One-offs aren't in this number. They have averaged $722.22 a month (in 1 of the last 9), so a month with the usual one-offs would come to about $12,587.22.",
    )
    expect(describeOneOffs({ ...DATA, one_offs: { ...DATA.one_offs, average_per_month: 0 } })).toBe('No one-offs in the last 9 months.')
  })

  it('lists each method with its error and marks the one used', () => {
    expect(describeCandidate(DATA.candidates[1])).toBe('Average of the last 3 months: off by 8.7% on average (used)')
    expect(describeCandidate({ ...DATA.candidates[0], mape: null })).toBe('Same as last month: off by n/a on average')
  })

  it('explains the range, or says nothing when there is none', () => {
    expect(describeRange(DATA)).toMatch(/only 5 tests\. About 80% of months should land inside it\./)
    expect(describeRange({ ...DATA, forecast: { point: 1, low: null, high: null } })).toBe('')
  })
})

describe('ForecastPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    client.fetchForecast.mockImplementation(async () => DATA)
  })

  it('shows the headline, the track record, the categories and the details', async () => {
    render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByTestId('forecast-sentence')).toBeTruthy()

    expect(client.fetchForecast).toHaveBeenCalledWith({ scope: 'all', spaceIds: [] })
    expect(screen.getByTestId('forecast-sentence').textContent).toMatch(/Oct 2026 is on track for about \$11,865\.00/)
    expect(screen.getByTestId('forecast-sofar').textContent).toMatch(/So far this month \(to the 21st\): \$9,750\.00/)
    expect(screen.getByTestId('forecast-accuracy').textContent).toMatch(/off by 8\.7% on average/)
    expect(screen.getByTestId('forecast-categories').textContent).toMatch(/Housing.*\$9,000\.00.*Groceries.*\$2,865\.00/)
    expect(screen.getByText(/One-offs aren't in this number/)).toBeTruthy()
    expect(screen.getByTestId('forecast-candidates').textContent).toMatch(/Same as last month.*Average of the last 3 months.*\(used\)/)
    expect(screen.getByText('How was this worked out?')).toBeTruthy()
  })

  it('colours a category that is expected to fall green and one expected to rise red', async () => {
    client.fetchForecast.mockImplementation(async () => ({
      ...DATA, categories: [{ ...DATA.categories[0], change: 120 }, { ...DATA.categories[1], change: -35 }],
    }))
    render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={null} />)
    await screen.findByTestId('forecast-categories')

    expect(screen.getByText('+$120.00').className).toMatch(/up/)
    expect(screen.getByText('-$35.00').className).toMatch(/down/)
  })

  it('renders without crashing when the API answers with an empty object', async () => {
    client.fetchForecast.mockImplementation(async () => ({}))
    render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect((await screen.findByTestId('forecast-sentence')).textContent).toMatch(/A forecast needs at least 3 finished months/)
    expect(screen.queryByTestId('forecast-chart')).toBeNull()
  })

  it('shows the reason instead of a chart when there is no forecast', async () => {
    client.fetchForecast.mockImplementation(async () => ({ ...DATA, available: false, reason: 'not_enough_history', months_available: 2 }))
    render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect((await screen.findByTestId('forecast-sentence')).textContent).toBe('A forecast needs at least 3 finished months of spending; you have 2.')
    expect(screen.queryByTestId('forecast-chart')).toBeNull()
  })

  it('notes that the first month was left out when recording began part-way through it', async () => {
    client.fetchForecast.mockImplementation(async () => ({ ...DATA, skipped_first_month: true }))
    render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByText(/Your first month was left out because recording began part-way through it/)).toBeTruthy()
  })

  it('mentions expenses left out for lack of an exchange rate', async () => {
    client.fetchForecast.mockImplementation(async () => ({ ...DATA, unconverted_count: 1 }))
    render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={null} />)

    expect(await screen.findByText(/1 expense in a currency without an exchange rate is left out/)).toBeTruthy()
  })

  it('reloads when the dashboard data is refreshed or the scope changes', async () => {
    const { rerender } = render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={{ a: 1 }} />)
    await screen.findByTestId('forecast-sentence')

    rerender(<ForecastPanel scope="all" spaceIds={[]} refreshKey={{ a: 2 }} />)
    await waitFor(() => expect(client.fetchForecast).toHaveBeenCalledTimes(2))
    rerender(<ForecastPanel scope="personal" spaceIds={[]} refreshKey={{ a: 2 }} />)

    await waitFor(() => expect(client.fetchForecast).toHaveBeenLastCalledWith({ scope: 'personal', spaceIds: [] }))
  })

  it('shows a message when loading fails, and keeps the last answer if a refresh fails', async () => {
    client.fetchForecast.mockRejectedValueOnce(new Error('boom'))
    const { rerender } = render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={1} />)
    expect(await screen.findByText(/Couldn’t load the forecast: boom/)).toBeTruthy()

    rerender(<ForecastPanel scope="all" spaceIds={[]} refreshKey={2} />)
    await screen.findByTestId('forecast-sentence')
    client.fetchForecast.mockRejectedValueOnce(new Error('later'))
    rerender(<ForecastPanel scope="all" spaceIds={[]} refreshKey={3} />)

    expect(await screen.findByText(/Couldn’t refresh: later/)).toBeTruthy()
    expect(screen.getByTestId('forecast-sentence')).toBeTruthy()
  })

  it('ignores a slow answer that arrives after a newer one', async () => {
    let releaseSlow
    client.fetchForecast
      .mockImplementationOnce(async () => DATA)
      .mockImplementationOnce(() => new Promise((r) => { releaseSlow = () => r({ ...DATA, model: { ...DATA.model, label: 'SLOW ANSWER' } }) }))
      .mockImplementationOnce(async () => ({ ...DATA, model: { ...DATA.model, label: 'NEWEST ANSWER' } }))
    const { rerender } = render(<ForecastPanel scope="all" spaceIds={[]} refreshKey={1} />)
    await screen.findByTestId('forecast-sentence')

    rerender(<ForecastPanel scope="all" spaceIds={[]} refreshKey={2} />) // slow
    await waitFor(() => expect(client.fetchForecast).toHaveBeenCalledTimes(2))
    rerender(<ForecastPanel scope="all" spaceIds={[]} refreshKey={3} />) // newer
    await screen.findByText(/NEWEST ANSWER/)
    releaseSlow()
    await new Promise((r) => setTimeout(r, 20))

    expect(screen.getByText(/NEWEST ANSWER/)).toBeTruthy()
    expect(screen.queryByText(/SLOW ANSWER/)).toBeNull()
  })
})

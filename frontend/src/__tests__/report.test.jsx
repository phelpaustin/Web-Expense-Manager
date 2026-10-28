import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>
  const None = () => null
  return { BarChart: Pass, Bar: Pass, Cell: None, LabelList: None, CartesianGrid: None, XAxis: None, YAxis: None, Tooltip: None, ResponsiveContainer: Pass }
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import {
  categoryChartHeight, changeDirection, changeText, chartCategories, describeCategoryChart, describePeriodChart, periodChartRows, summaryText, tickLabel, yearChoices,
} from '../report.js'
import ReportPanel from '../components/ReportPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())

const NOW = new Date()
const THIS_YEAR = NOW.getFullYear()
const THIS_MONTH = NOW.getMonth() + 1

const cat = (category, total, share, count = 2) => ({ category, total, share_pct: share, count })
const REPORT = (extra = {}) => ({
  kind: 'year', year: 2026, month: null, label: '2026', start: '2026-01-01', end: '2026-12-31', years: [2026, 2025], currency: 'USD', unconverted_count: 0,
  totals: { spent: 1000, count: 12, income: 3000, net: 2000, savings_rate_pct: 66.7, avg_per_day: 3.3, avg_per_month: 100 },
  previous: { label: '2025', spent: 800, count: 9, change: 200, change_pct: 25 },
  categories: [cat('Rent', 600, 60), cat('Food', 300, 30), cat('Fun', 100, 10)],
  periods: [{ key: '2026-01', label: 'Jan', total: 400, count: 5 }, { key: '2026-02', label: 'Feb', total: 600, count: 7 }],
  peak: { key: '2026-02', label: 'February', total: 600 },
  top_shops: [{ shop: 'ICA', total: 250, count: 8, share_pct: 25 }],
  largest: [{ date: '2026-02-11', category: 'Rent', description: 'Rent', shop: 'Landlord', amount: 600 }],
  category_matrix: null, ...extra,
})
const show = (props = {}) => render(<ReportPanel scope="personal" refreshKey={0} {...props} />)

describe('report helpers', () => {
  it('offers the years with data plus the selected one, newest first', () => {
    expect(yearChoices([2024, 2026], 2025)).toEqual([2026, 2025, 2024])
    expect(yearChoices([2026], 2026)).toEqual([2026])
    expect(yearChoices(undefined, 2026)).toEqual([2026])
    expect(yearChoices(null, undefined)).toEqual([])
  })

  it('says how spending changed, or why there is nothing to compare with', () => {
    expect(changeText(REPORT())).toBe('▲ 25% vs 2025 ($800.00)')
    expect(changeText(REPORT({ previous: { label: '2025', spent: 800, change: -200, change_pct: -25 } }))).toBe('▼ 25% vs 2025 ($800.00)')
    expect(changeText(REPORT({ previous: { label: 'March 2026', spent: 0, change: 50, change_pct: null } }))).toBe('Nothing recorded in March 2026 to compare with.')
    expect(changeDirection(REPORT())).toBe('up')
    expect(changeDirection(REPORT({ previous: { label: 'x', spent: 5, change: -1, change_pct: -20 } }))).toBe('down')
  })

  it('summarises the report in words', () => {
    expect(summaryText(REPORT())).toBe('You spent $1,000.00 in 2026 across 12 expenses. Rent was the biggest category at 60%. The highest month was February ($600.00).')
    expect(summaryText(REPORT({ kind: 'month', label: 'February 2026', peak: { label: '11 February', total: 300 } }))).toContain('The highest day was 11 February ($300.00).')
    expect(summaryText(REPORT({ totals: { ...REPORT().totals, count: 1 }, categories: [cat('Rent', 5, 100)], peak: null }))).toBe('You spent $1,000.00 in 2026 across 1 expense.')
    expect(summaryText(REPORT({ totals: { ...REPORT().totals, count: 0 } }))).toBe('No spending recorded in 2026.')
  })

  it('draws the biggest categories and groups the rest as Other', () => {
    const many = Array.from({ length: 15 }, (_, i) => cat(`C${i}`, 100 - i, 5, 2))
    const rows = chartCategories(many)
    expect(rows).toHaveLength(13)
    expect(rows[0]).toEqual({ name: 'C0', total: 100, share_pct: 5, count: 2 })
    expect(rows[12]).toEqual({ name: 'Other (3)', total: 88 + 87 + 86, share_pct: 15, count: 6, other: true })
    expect(chartCategories(many.slice(0, 12))).toHaveLength(12)
    expect(chartCategories([])).toEqual([])
    expect(chartCategories(many, 2).map((r) => r.name)).toEqual(['C0', 'C1', 'Other (13)'])
  })

  it('shortens month labels to a letter on a phone, never day numbers or desktop labels', () => {
    expect(tickLabel('Jan', false, true)).toBe('J')
    expect(tickLabel('Jan', false, false)).toBe('Jan')
    expect(tickLabel('12', true, true)).toBe('12')
  })

  it('sizes the chart to the number of bars', () => {
    expect(categoryChartHeight(new Array(3).fill(0))).toBe(120)
    expect(categoryChartHeight(new Array(13).fill(0))).toBe(410)
  })

  it('describes the charts in words for screen readers', () => {
    expect(describeCategoryChart(chartCategories(REPORT().categories))).toBe('Bar chart of spending by category: Rent $600.00, Food $300.00, Fun $100.00.')
    expect(describePeriodChart(REPORT())).toBe('Bar chart of spending by month. Highest month: February, $600.00.')
    expect(describePeriodChart(REPORT({ kind: 'month', peak: null }))).toBe('Bar chart of spending by day.')
    expect(periodChartRows(REPORT().periods)[1]).toEqual({ key: '2026-02', name: 'Feb', total: 600, count: 7 })
  })
})

describe('ReportPanel', () => {
  it('shows the report for this year first', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    show()
    await screen.findByTestId('report-title')
    expect(client.fetchReport).toHaveBeenCalledWith({ year: THIS_YEAR, month: undefined, scope: 'personal', spaceIds: undefined })
    expect(screen.getByTestId('report-title').textContent).toBe('2026')
    expect(screen.getByTestId('report-summary').textContent).toContain('You spent $1,000.00 in 2026')
    expect(screen.getByTestId('report-change').textContent).toBe('▲ 25% vs 2025 ($800.00)')
    expect(screen.getByText('Net $2,000.00 · saved 66.7%')).toBeTruthy()
    expect(screen.getByText('$100.00 per month')).toBeTruthy()
  })

  it('charts the categories and lists every one with amount, share and count', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    show()
    const chart = await screen.findByTestId('report-category-chart')
    expect(chart.getAttribute('aria-label')).toContain('Rent $600.00')
    expect(screen.getByTestId('report-period-chart').getAttribute('aria-label')).toContain('Highest month: February')
    const table = screen.getAllByRole('table')[0]
    const rows = within(table).getAllByRole('row').map((r) => r.textContent)
    expect(rows[1]).toBe('Rent$600.0060%2')
    expect(rows).toHaveLength(1 + 3 + 1)
    expect(rows[4]).toBe('Total$1,000.00' + '12')
  })

  it('lists the top shops and the largest expenses', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    show()
    await screen.findByText(/Top shops/)
    expect(screen.getByText('ICA')).toBeTruthy()
    expect(screen.getByText(/Largest expenses/)).toBeTruthy()
    expect(screen.getByText('Landlord')).toBeTruthy()
    expect(screen.getByText('2026-02-11')).toBeTruthy()
  })

  it('switches to a month and asks for it', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    show()
    await screen.findByTestId('report-title')
    expect(screen.queryByLabelText('Report month')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    await waitFor(() => expect(client.fetchReport).toHaveBeenLastCalledWith({ year: THIS_YEAR, month: THIS_MONTH, scope: 'personal', spaceIds: undefined }))
    expect(screen.getByRole('button', { name: 'Month' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Year' }).getAttribute('aria-pressed')).toBe('false')
    fireEvent.change(screen.getByLabelText('Report month'), { target: { value: '3' } })
    await waitFor(() => expect(client.fetchReport).toHaveBeenLastCalledWith({ year: THIS_YEAR, month: 3, scope: 'personal', spaceIds: undefined }))
    fireEvent.click(screen.getByRole('button', { name: 'Year' }))
    await waitFor(() => expect(client.fetchReport).toHaveBeenLastCalledWith({ year: THIS_YEAR, month: undefined, scope: 'personal', spaceIds: undefined }))
  })

  it('offers the years that have data and asks for the one picked', async () => {
    client.fetchReport.mockResolvedValue(REPORT({ years: [THIS_YEAR, 2025, 2023] }))
    show()
    await screen.findByTestId('report-title')
    const select = screen.getByLabelText('Report year')
    expect([...select.options].map((o) => o.value)).toEqual([String(THIS_YEAR), '2025', '2023'])
    fireEvent.change(select, { target: { value: '2023' } })
    await waitFor(() => expect(client.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ year: 2023 })))
  })

  it('downloads the Excel file and the PDF for what is on screen', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    client.downloadReport.mockResolvedValue(undefined)
    show({ spaceIds: ['personal', '4'] })
    await screen.findByTestId('report-title')
    fireEvent.click(screen.getByRole('button', { name: 'Download Excel' }))
    expect(client.downloadReport).toHaveBeenLastCalledWith({ format: 'xlsx', year: THIS_YEAR, month: undefined, scope: 'personal', spaceIds: ['personal', '4'] })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Download Excel' }).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    await waitFor(() => expect(client.fetchReport).toHaveBeenLastCalledWith(expect.objectContaining({ month: THIS_MONTH })))
    fireEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
    expect(client.downloadReport).toHaveBeenLastCalledWith({ format: 'pdf', year: THIS_YEAR, month: THIS_MONTH, scope: 'personal', spaceIds: ['personal', '4'] })
  })

  it('disables both download buttons while one is being prepared', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    let finish
    client.downloadReport.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    show()
    await screen.findByTestId('report-title')
    fireEvent.click(screen.getByRole('button', { name: 'Download PDF' }))
    expect(screen.getByRole('button', { name: 'Preparing…' }).disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Download Excel' }).disabled).toBe(true)
    finish()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Download PDF' }).disabled).toBe(false))
  })

  it('says when a download fails and lets you try again', async () => {
    client.fetchReport.mockResolvedValue(REPORT())
    client.downloadReport.mockRejectedValueOnce(new Error('Couldn’t create the report file'))
    show()
    await screen.findByTestId('report-title')
    fireEvent.click(screen.getByRole('button', { name: 'Download Excel' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('alert').textContent).toBe('Couldn’t create the report file')
    client.downloadReport.mockResolvedValueOnce(undefined)
    fireEvent.click(screen.getByRole('button', { name: 'Download Excel' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('shows a short note and no charts or tables when nothing was spent', async () => {
    client.fetchReport.mockResolvedValue(REPORT({
      totals: { spent: 0, count: 0, income: 0, net: 0, savings_rate_pct: null, avg_per_day: 0, avg_per_month: 0 },
      categories: [], top_shops: [], largest: [], peak: null, previous: { label: '2025', spent: 0, count: 0, change: 0, change_pct: null },
    }))
    show()
    await screen.findByText('No spending recorded in 2026.')
    expect(screen.queryByTestId('report-category-chart')).toBeNull()
    expect(screen.queryByTestId('report-period-chart')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByRole('button', { name: 'Download PDF' })).toBeTruthy()
  })

  it('mentions expenses that were left out for lack of an exchange rate', async () => {
    client.fetchReport.mockResolvedValue(REPORT({ unconverted_count: 1 }))
    show()
    await screen.findByText('1 expense is left out because its currency has no exchange rate.')
    client.fetchReport.mockResolvedValue(REPORT({ unconverted_count: 3 }))
    show()
    await screen.findByText('3 expenses are left out because its currency has no exchange rate.')
  })

  it('shows Loading until the report has its shape, and an error when the request fails', async () => {
    client.fetchReport.mockResolvedValue({})
    const { unmount } = show()
    expect(screen.getByText('Loading…')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Download Excel' })).toBeTruthy()          // the controls stay usable
    unmount()
    client.fetchReport.mockRejectedValue(new Error('boom'))
    show()
    await waitFor(() => expect(screen.getByText(/Couldn’t load the report: boom/)).toBeTruthy())
  })

  it('keeps the last report and says so when a refresh fails', async () => {
    client.fetchReport.mockResolvedValueOnce(REPORT())
    show()
    await screen.findByTestId('report-title')
    client.fetchReport.mockRejectedValueOnce(new Error('offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    await screen.findByText(/Couldn’t refresh: offline/)
    expect(screen.getByTestId('report-title').textContent).toBe('2026')
  })

  it('ignores a slow answer to a request that has been replaced', async () => {
    let slow
    client.fetchReport.mockImplementationOnce(() => new Promise((resolve) => { slow = resolve }))
    client.fetchReport.mockResolvedValue(REPORT({ label: 'March 2026', kind: 'month' }))
    show()
    fireEvent.click(screen.getByRole('button', { name: 'Month' }))
    await screen.findByText('March 2026')
    slow(REPORT({ label: 'OLD' }))
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByText('OLD')).toBeNull()
    expect(screen.getByTestId('report-title').textContent).toBe('March 2026')
  })
})

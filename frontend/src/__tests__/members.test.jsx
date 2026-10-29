import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>
  const None = () => null
  return { BarChart: Pass, Bar: Pass, Cell: None, CartesianGrid: None, XAxis: None, YAxis: None, Tooltip: None, ResponsiveContainer: Pass }
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import {
  PERIODS, cellAmount, describeBars, memberBars, memberColors, memberLabel, OTHER_COLOR, periodLabel, periodRange, sharesText, spacesText, summaryText,
  topCategoriesText, trendRows,
} from '../members.js'
import MembersPanel from '../components/MembersPanel.jsx'

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())

const ann = { user_id: 1, name: 'Ann', email: 'ann@x.com', is_me: true, total: 400, count: 2, share_pct: 80, avg_per_expense: 200, top_categories: [{ category: 'Rent', total: 300 }, { category: 'Food', total: 100 }] }
const bob = { user_id: 2, name: '', email: 'bob@x.com', is_me: false, total: 100, count: 1, share_pct: 20, avg_per_expense: 100, top_categories: [{ category: 'Fun', total: 100 }] }
const cat = { user_id: 3, name: 'Cat', email: 'cat@x.com', is_me: false, total: 0, count: 0, share_pct: 0, avg_per_expense: 0, top_categories: [] }
const DATA = (extra = {}) => ({
  date_from: '2026-10-01', date_to: '2026-10-28', member_count: 3, total: 500, count: 3, members: [ann, bob, cat],
  categories: [
    { category: 'Rent', total: 300, by_member: [{ user_id: 1, total: 300 }, { user_id: 2, total: 0 }, { user_id: 3, total: 0 }] },
    { category: 'Other', other: true, count: 2, total: 200, by_member: [{ user_id: 1, total: 100 }, { user_id: 2, total: 100 }, { user_id: 3, total: 0 }] },
  ],
  months: [
    { month: '2026-09', total: 150, by_member: [{ user_id: 1, total: 100 }, { user_id: 2, total: 50 }, { user_id: 3, total: 0 }] },
    { month: '2026-10', total: 350, by_member: [{ user_id: 1, total: 300 }, { user_id: 2, total: 50 }, { user_id: 3, total: 0 }] },
  ],
  months_total: 2, spaces: [{ id: 10, name: 'Home', space_type: 'household' }, { id: 11, name: 'Goa', space_type: 'trip' }], currency: 'USD', unconverted_count: 0, ...extra,
})
const show = (props = {}) => render(<MemoryRouter><MembersPanel scope="all" refreshKey={0} {...props} /></MemoryRouter>)

describe('period ranges', () => {
  const now = new Date(2026, 9, 28)             // 28 Oct 2026, local time
  it('covers this month so far, last month, 90 days, this year and all time', () => {
    expect(periodRange('this_month', now)).toEqual({ dateFrom: '2026-10-01', dateTo: '2026-10-28' })
    expect(periodRange('last_month', now)).toEqual({ dateFrom: '2026-09-01', dateTo: '2026-09-30' })
    expect(periodRange('last_90', now)).toEqual({ dateFrom: '2026-07-31', dateTo: '2026-10-28' })
    expect(periodRange('this_year', now)).toEqual({ dateFrom: '2026-01-01', dateTo: '2026-10-28' })
    expect(periodRange('all', now)).toEqual({ dateFrom: undefined, dateTo: undefined })
  })

  it('handles January (last month is December of the year before) and a leap February', () => {
    expect(periodRange('last_month', new Date(2026, 0, 15))).toEqual({ dateFrom: '2025-12-01', dateTo: '2025-12-31' })
    expect(periodRange('last_month', new Date(2028, 2, 5))).toEqual({ dateFrom: '2028-02-01', dateTo: '2028-02-29' })
    expect(periodRange('last_90', new Date(2026, 1, 10))).toEqual({ dateFrom: '2025-11-13', dateTo: '2026-02-10' })
  })

  it('labels the periods, falling back to the first', () => {
    expect(PERIODS.map((p) => p.key)).toEqual(['this_month', 'last_month', 'last_90', 'this_year', 'all'])
    expect(periodLabel('last_90')).toBe('Last 90 days')
    expect(periodLabel('nonsense')).toBe('This month')
  })
})

describe('member helpers', () => {
  it('names a member by name, else email, and marks the viewer', () => {
    expect(memberLabel(ann)).toBe('Ann (you)')
    expect(memberLabel(bob)).toBe('bob@x.com')
    expect(memberLabel({ user_id: null, name: '', email: '' })).toBe('Unknown')
    expect(memberLabel({ user_id: 9, name: '', email: '' })).toBe('Member')
  })

  it('gives each member a colour by id, not by rank, and greys out past the palette', () => {
    const a = memberColors([bob, ann, cat])
    expect(new Set([a.get(1), a.get(2), a.get(3)]).size).toBe(3)
    expect(memberColors([ann, bob, cat]).get(2)).toBe(a.get(2))                       // order of the list does not matter
    const many = memberColors(Array.from({ length: 10 }, (_, i) => ({ user_id: i + 1 })))
    expect(many.get(8)).not.toBe(OTHER_COLOR)
    expect(many.get(9)).toBe(OTHER_COLOR)
    const unowned = memberColors([{ user_id: null }, { user_id: 4 }])      // an expense with no owner comes after the real members
    expect(unowned.get(4)).toBe('#6d7bff')
    expect(unowned.get(null)).toBe('#10b981')
  })

  it('makes a bar per member and a row per month', () => {
    const bars = memberBars(DATA())
    expect(bars.map((b) => [b.name, b.total, b.share_pct])).toEqual([['Ann (you)', 400, 80], ['bob@x.com', 100, 20], ['Cat', 0, 0]])
    expect(describeBars(bars)).toBe('Bar chart of spending by member: Ann (you) $400.00, bob@x.com $100.00, Cat $0.00.')
    const rows = trendRows(DATA())
    expect(rows[0]).toEqual({ month: '2026-09', name: 'Sep 26', total: 150, m1: 100, m2: 50, m3: 0 })
    expect(rows[1].name).toBe('Oct 26')
  })

  it('writes the shares, leaving out members who spent nothing', () => {
    expect(sharesText(DATA())).toBe('Ann (you) 80% · bob@x.com 20%')
  })

  it('names the spaces in a sentence', () => {
    expect(spacesText([])).toBe('')
    expect(spacesText([{ name: 'Home' }])).toBe('In Home')
    expect(spacesText([{ name: 'Home' }, { name: 'Goa' }])).toBe('Across Home and Goa')
    expect(spacesText([{ name: 'A' }, { name: 'B' }, { name: 'C' }])).toBe('Across A, B and C')
  })

  it('summarises, or says why there is nothing', () => {
    expect(summaryText(DATA())).toBe('$500.00 was spent in 3 expenses. Ann (you) paid the most: 80%.')
    expect(summaryText(DATA({ count: 1, total: 20, members: [ann] }))).toBe('$20.00 was spent in 1 expense.')
    expect(summaryText(DATA({ count: 0 }))).toBe('Nothing was spent in the shared spaces in this period.')
    expect(summaryText(DATA({ spaces: [] }))).toBe('Spending by member needs a shared space with other people in it.')
  })

  it('reads a category cell and a member’s top categories', () => {
    expect(cellAmount(DATA().categories[1], 2)).toBe(100)
    expect(cellAmount(DATA().categories[1], 99)).toBe(0)
    expect(topCategoriesText(ann)).toBe('Rent $300.00, Food $100.00')
    expect(topCategoriesText(cat)).toBe('')
  })
})

describe('MembersPanel', () => {
  it('asks for this month by default and shows everyone', async () => {
    client.fetchMembers.mockResolvedValue(DATA())
    show()
    await screen.findByTestId('members-summary')
    const call = client.fetchMembers.mock.calls[0][0]
    expect(call.scope).toBe('all')
    expect(call.dateFrom).toMatch(/^\d{4}-\d{2}-01$/)
    expect(call.dateTo).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(screen.getByText('Across Home and Goa')).toBeTruthy()
    expect(screen.getByTestId('members-summary').textContent).toBe('$500.00 was spent in 3 expenses. Ann (you) paid the most: 80%.')
    expect(screen.getByTestId('members-chart').getAttribute('aria-label')).toContain('Ann (you) $400.00')
  })

  it('lists each member with spent, share, expenses, average and what they spend on', async () => {
    client.fetchMembers.mockResolvedValue(DATA())
    show()
    const row = await screen.findByTestId('member-1')
    expect(row.textContent).toBe('Ann (you)$400.0080%2$200.00Rent $300.00, Food $100.00')
    expect(screen.getByTestId('member-2').textContent).toBe('bob@x.com$100.0020%1$100.00Fun $100.00')
    expect(screen.getByTestId('member-3').textContent).toBe('Cat$0.000%0––')              // nothing spent: dashes, not $0.00 averages
  })

  it('shows the member-by-category table with a dash where a member spent nothing', async () => {
    client.fetchMembers.mockResolvedValue(DATA())
    show()
    const table = await screen.findByTestId('members-categories')
    const rows = within(table).getAllByRole('row').map((r) => r.textContent)
    expect(rows[0]).toBe('CategoryAnn (you)bob@x.comCatTotal')
    expect(rows[1]).toBe('Rent$300.00––$300.00')
    expect(rows[2]).toBe('Other (2 categories)$100.00$100.00–$200.00')
  })

  it('shows the monthly chart and its legend when there are at least two months, else leaves it out', async () => {
    client.fetchMembers.mockResolvedValue(DATA())
    const { unmount } = show()
    await screen.findByTestId('members-trend')
    expect(screen.getByTestId('members-legend').textContent).toContain('Ann (you)')
    unmount()
    client.fetchMembers.mockResolvedValue(DATA({ months: [DATA().months[0]], months_total: 1 }))
    show()
    await screen.findByTestId('members-summary')
    expect(screen.queryByTestId('members-trend')).toBeNull()
  })

  it('says when only the latest months are shown', async () => {
    client.fetchMembers.mockResolvedValue(DATA({ months_total: 40 }))
    show()
    await screen.findByText('Showing the latest 2 of 40 months.')
  })

  it('hides the category table when only one person is in the space', async () => {
    client.fetchMembers.mockResolvedValue(DATA({ member_count: 1, members: [ann], total: 400, count: 2, spaces: [{ id: 10, name: 'Home' }] }))
    show()
    await screen.findByText('Only you are in this space so far.')
    expect(screen.queryByTestId('members-categories')).toBeNull()
  })

  it('points to the Settings page for spaces when there is none to look at', async () => {
    client.fetchMembers.mockResolvedValue(DATA({ spaces: [], members: [], categories: [], months: [], months_total: 0, count: 0, total: 0, member_count: 0 }))
    show()
    await screen.findByText('Spending by member needs a shared space with other people in it.')
    expect(screen.getByRole('link', { name: /set one up and invite people/ }).getAttribute('href')).toBe('/settings?tab=spaces')
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByTestId('members-chart')).toBeNull()
  })

  it('shows the members but no charts when nothing was spent', async () => {
    client.fetchMembers.mockResolvedValue(DATA({ count: 0, total: 0, categories: [], months: [], months_total: 0, members: [{ ...ann, total: 0, count: 0, share_pct: 0, top_categories: [] }, bob] }))
    show()
    await screen.findByText('Nothing was spent in the shared spaces in this period.')
    expect(screen.queryByTestId('members-chart')).toBeNull()
    expect(screen.getByTestId('member-1')).toBeTruthy()
  })

  it('asks again when the period changes', async () => {
    client.fetchMembers.mockResolvedValue(DATA())
    show()
    await screen.findByTestId('members-summary')
    fireEvent.change(screen.getByLabelText('Members period'), { target: { value: 'all' } })
    await waitFor(() => expect(client.fetchMembers).toHaveBeenLastCalledWith({ dateFrom: undefined, dateTo: undefined, scope: 'all', spaceIds: undefined }))
    fireEvent.change(screen.getByLabelText('Members period'), { target: { value: 'this_year' } })
    await waitFor(() => expect(client.fetchMembers.mock.calls.at(-1)[0].dateFrom).toMatch(/^\d{4}-01-01$/))
  })

  it('passes the chosen spaces on', async () => {
    client.fetchMembers.mockResolvedValue(DATA())
    show({ scope: 'all', spaceIds: ['10', '11'] })
    await screen.findByTestId('members-summary')
    expect(client.fetchMembers.mock.calls[0][0].spaceIds).toEqual(['10', '11'])
  })

  it('mentions expenses left out for lack of an exchange rate', async () => {
    client.fetchMembers.mockResolvedValue(DATA({ unconverted_count: 2 }))
    show()
    await screen.findByText('2 expenses are left out because its currency has no exchange rate.')
  })

  it('shows Loading until the data has its shape, and an error when the request fails', async () => {
    client.fetchMembers.mockResolvedValue({})
    const { unmount } = show()
    expect(screen.getByText('Loading…')).toBeTruthy()
    unmount()
    client.fetchMembers.mockRejectedValue(new Error('boom'))
    show()
    await waitFor(() => expect(screen.getByText(/Couldn’t load this: boom/)).toBeTruthy())
  })

  it('keeps the last answer and says so when a refresh fails', async () => {
    client.fetchMembers.mockResolvedValueOnce(DATA())
    show()
    await screen.findByTestId('members-summary')
    client.fetchMembers.mockRejectedValueOnce(new Error('offline'))
    fireEvent.change(screen.getByLabelText('Members period'), { target: { value: 'last_month' } })
    await screen.findByText(/Couldn’t refresh: offline/)
    expect(screen.getByTestId('members-summary')).toBeTruthy()
  })
})

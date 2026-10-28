import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import { setDisplayCurrency } from '../format.js'
import {
  barPercent, contributionBody, contributionText, daysLeftText, formatDate, goalBody, paceText, savedText, statusInfo, summaryText, todayLocal,
} from '../savings.js'
import SavingsPage from '../pages/SavingsPage.jsx'

// Intl puts a no-break space between a currency code and the number; compare with a plain one.
const plain = (text) => text.replace(/\u00a0/g, ' ')

beforeAll(() => setDisplayCurrency('USD'))
beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

const goal = (extra = {}) => ({
  id: 1, name: 'Trip', note: '', currency: 'SEK', target_amount: 10000, target_date: '2027-03-05',
  saved: 3000, remaining: 7000, pct: 30, reached: false, status: 'on_track', days_left: 128,
  needed_per_month: 1600, recent_per_month: 2000, shortfall_per_month: null, projected_date: '2027-02-01', contribution_count: 2, last_contribution: '2026-10-20', ...extra,
})
const LIST = (goals, extra = {}) => ({ goals, summary: { goals: goals.length, reached: 0, behind: 0 }, limit: 50, ...extra })
const show = (props = {}) => render(<SavingsPage currencies={['SEK', 'EUR']} baseCurrency="SEK" {...props} />)

describe('savings helpers', () => {
  it('formats a date from its text, never through a time zone', () => {
    expect(formatDate('2027-03-05')).toBe('5 Mar 2027')
    expect(formatDate('2026-12-31')).toBe('31 Dec 2026')
    expect(formatDate('2027-03-05T23:30:00')).toBe('5 Mar 2027')
    expect(formatDate(null)).toBe('')
    expect(formatDate('nonsense')).toBe('')
  })

  it("gives today's date in the person's own calendar", () => {
    expect(todayLocal(new Date(2026, 9, 28, 0, 5))).toBe('2026-10-28')        // just after midnight local, still the 28th
    expect(todayLocal(new Date(2026, 0, 3, 23, 59))).toBe('2026-01-03')
  })

  it('knows each status', () => {
    expect(statusInfo('reached')).toEqual({ label: 'Reached', tone: 'good' })
    expect(statusInfo('behind').tone).toBe('bad')
    expect(statusInfo('overdue').tone).toBe('bad')
    expect(statusInfo('no_deadline').tone).toBe('neutral')
    expect(statusInfo('something new').label).toBe('No deadline')
  })

  it('sizes the bar: never past full, any progress visible', () => {
    expect(barPercent({ pct: 30 })).toBe(30)
    expect(barPercent({ pct: 150 })).toBe(100)
    expect(barPercent({ pct: 0.2 })).toBe(1)
    expect(barPercent({ pct: 0 })).toBe(0)
    expect(barPercent({ pct: -5 })).toBe(0)
  })

  it('says how much is saved in the goal’s own currency', () => {
    expect(plain(savedText(goal()))).toBe('SEK 3,000.00 of SEK 10,000.00')
    expect(savedText(goal({ currency: 'USD' }))).toBe('$3,000.00 of $10,000.00')
  })

  it('explains each situation in words', () => {
    expect(plain(paceText(goal({ status: 'reached' })))).toBe('You’ve reached this goal.')
    expect(plain(paceText(goal({ status: 'overdue' })))).toBe('The target date (5 Mar 2027) has passed with SEK 7,000.00 still to go.')
    expect(plain(paceText(goal()))).toBe('At your recent pace of SEK 2,000.00 a month you’d get there around 1 Feb 2027, in time for 5 Mar 2027.')
    expect(plain(paceText(goal({ status: 'behind', shortfall_per_month: 700, needed_per_month: 2700 })))).toBe(
      'To reach it by 5 Mar 2027 you need SEK 2,700.00 a month. You’re saving SEK 2,000.00 a month, SEK 700.00 short.',
    )
    expect(plain(paceText(goal({ status: 'behind', recent_per_month: 0, needed_per_month: 2700, projected_date: null })))).toBe(
      'To reach it by 5 Mar 2027 you need SEK 2,700.00 a month, and nothing has been added in the last 90 days.',
    )
    expect(paceText(goal({ status: 'no_deadline', target_date: null }))).toContain('around 1 Feb 2027')
    expect(plain(paceText(goal({ status: 'no_deadline', target_date: null, projected_date: null, recent_per_month: 0 })))).toBe('No target date. Add money and you’ll see when you’d get there.')
  })

  it('counts the days left', () => {
    expect(daysLeftText(goal())).toBe('128 days left')
    expect(daysLeftText(goal({ days_left: 1 }))).toBe('1 day left')
    expect(daysLeftText(goal({ days_left: 0 }))).toBe('Due today')
    expect(daysLeftText(goal({ days_left: -3, status: 'overdue' }))).toBe('Passed 3 days ago')
    expect(daysLeftText(goal({ days_left: -1, status: 'overdue' }))).toBe('Passed 1 day ago')
    expect(daysLeftText(goal({ days_left: null }))).toBe('')
    expect(daysLeftText(goal({ status: 'reached' }))).toBe('')
  })

  it('summarises the list', () => {
    expect(summaryText({ goals: 3, reached: 1, behind: 1 })).toBe('3 goals · 1 reached · 1 behind')
    expect(summaryText({ goals: 1, reached: 0, behind: 0 })).toBe('1 goal')
    expect(summaryText({ goals: 0, reached: 0, behind: 0 })).toBe('')
    expect(summaryText(null)).toBe('')
  })

  it('describes a deposit or a withdrawal', () => {
    expect(plain(contributionText({ amount: 250, date: '2026-10-03', note: 'bonus' }, 'SEK'))).toBe('Added SEK 250.00 on 3 Oct 2026: bonus')
    expect(plain(contributionText({ amount: -80, date: '2026-10-04', note: '' }, 'SEK'))).toBe('Withdrew SEK 80.00 on 4 Oct 2026')
  })

  it('builds the add-money request, or says what is wrong', () => {
    expect(contributionBody({ kind: 'deposit', amount: '250', date: '2026-10-03', note: ' hi ' })).toEqual({ body: { amount: '250', note: 'hi', date: '2026-10-03' } })
    expect(contributionBody({ kind: 'withdraw', amount: '80.5', date: '', note: '' })).toEqual({ body: { amount: '-80.5', note: '' } })
    for (const amount of ['', '0', '-5', 'abc', '0.001']) expect(contributionBody({ kind: 'deposit', amount, date: '', note: '' }).error).toBeTruthy()
  })

  it('builds the goal request, or says what is wrong', () => {
    const form = { name: ' Trip ', target: '5000', currency: 'EUR', targetDate: '2027-01-01', note: ' x ' }
    expect(goalBody(form)).toEqual({ body: { name: 'Trip', target_amount: '5000', target_date: '2027-01-01', note: 'x', currency: 'EUR' } })
    expect(goalBody({ ...form, currency: '', targetDate: '' }).body).toEqual({ name: 'Trip', target_amount: '5000', target_date: null, note: 'x' })
    expect(goalBody(form, { includeCurrency: false }).body.currency).toBeUndefined()
    expect(goalBody({ ...form, name: '  ' }).error).toBe('Give the goal a name.')
    expect(goalBody({ ...form, target: '0' }).error).toBe('The target must be above zero.')
    expect(goalBody({ ...form, target: '' }).error).toBeTruthy()
  })
})

describe('SavingsPage', () => {
  it('lists the goals with progress and what they need', async () => {
    client.fetchSavingsGoals.mockResolvedValue(LIST([goal(), goal({ id: 2, name: 'Laptop', status: 'behind', pct: 5, saved: 500, shortfall_per_month: 100 })], { summary: { goals: 2, reached: 0, behind: 1 } }))
    show()
    await screen.findByText('Trip')
    expect(screen.getByText('Laptop')).toBeTruthy()
    expect(screen.getByText('SEK 3,000.00 of SEK 10,000.00')).toBeTruthy()
    expect(screen.getByText('On track')).toBeTruthy()
    expect(screen.getByText('Behind')).toBeTruthy()
    const bar = screen.getByRole('progressbar', { name: 'Trip progress' })
    expect(bar.getAttribute('aria-valuenow')).toBe('30')
    expect(screen.getByTestId('savings-summary').textContent).toBe('2 goals · 1 behind')
    expect(screen.getAllByText(/Target date 5 Mar 2027 · 128 days left/).length).toBe(2)
  })

  it('shows a prompt when there are no goals', async () => {
    client.fetchSavingsGoals.mockResolvedValue(LIST([]))
    show()
    await screen.findByText(/No savings goals yet/)
    expect(screen.queryByTestId('savings-summary')).toBeNull()
  })

  it('shows Loading until the list has its shape, and an error when the request fails', async () => {
    client.fetchSavingsGoals.mockResolvedValue({})
    const { unmount } = show()
    expect(screen.getByText('Loading…')).toBeTruthy()
    unmount()
    client.fetchSavingsGoals.mockRejectedValue(new Error('boom'))
    show()
    await screen.findByText(/Couldn’t load your savings goals: boom/)
  })

  it('creates a goal and shows the refreshed list', async () => {
    client.fetchSavingsGoals.mockResolvedValueOnce(LIST([]))
    client.createSavingsGoal.mockResolvedValue({ id: 5 })
    show()
    await screen.findByText(/No savings goals yet/)
    fireEvent.click(screen.getByRole('button', { name: '➕ New goal' }))
    const form = screen.getByRole('form', { name: 'New savings goal' })
    fireEvent.change(within(form).getByLabelText('Goal name'), { target: { value: ' Bike ' } })
    fireEvent.change(within(form).getByLabelText('Target amount'), { target: { value: '4500' } })
    fireEvent.change(within(form).getByLabelText('Target date'), { target: { value: '2027-06-01' } })
    client.fetchSavingsGoals.mockResolvedValueOnce(LIST([goal({ id: 5, name: 'Bike', target_amount: 4500 })]))
    fireEvent.click(within(form).getByRole('button', { name: 'Create goal' }))
    await screen.findByText('Bike')
    expect(client.createSavingsGoal).toHaveBeenCalledWith({ name: 'Bike', target_amount: '4500', target_date: '2027-06-01', note: '' })
    expect(screen.queryByRole('form', { name: 'New savings goal' })).toBeNull()               // the form closes
  })

  it('sends the chosen currency', async () => {
    client.fetchSavingsGoals.mockResolvedValue(LIST([]))
    client.createSavingsGoal.mockResolvedValue({})
    show()
    await screen.findByText(/No savings goals yet/)
    fireEvent.click(screen.getByRole('button', { name: '➕ New goal' }))
    const form = screen.getByRole('form', { name: 'New savings goal' })
    expect(within(form).getByRole('option', { name: 'Default (SEK)' })).toBeTruthy()
    fireEvent.change(within(form).getByLabelText('Goal name'), { target: { value: 'Rome' } })
    fireEvent.change(within(form).getByLabelText('Target amount'), { target: { value: '800' } })
    fireEvent.change(within(form).getByTitle('Currency'), { target: { value: 'EUR' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Create goal' }))
    await waitFor(() => expect(client.createSavingsGoal).toHaveBeenCalledWith(expect.objectContaining({ currency: 'EUR' })))
  })

  it('does not send a goal without a name or a target, and shows what the server says when it refuses', async () => {
    client.fetchSavingsGoals.mockResolvedValue(LIST([]))
    show()
    await screen.findByText(/No savings goals yet/)
    fireEvent.click(screen.getByRole('button', { name: '➕ New goal' }))
    const form = screen.getByRole('form', { name: 'New savings goal' })
    fireEvent.click(within(form).getByRole('button', { name: 'Create goal' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Give the goal a name.')
    fireEvent.change(within(form).getByLabelText('Goal name'), { target: { value: 'Bike' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Create goal' }))
    expect((await screen.findByRole('alert')).textContent).toBe('The target must be above zero.')
    expect(client.createSavingsGoal).not.toHaveBeenCalled()
    fireEvent.change(within(form).getByLabelText('Target amount'), { target: { value: '100' } })
    client.createSavingsGoal.mockRejectedValue(new Error('You can have up to 50 savings goals'))
    fireEvent.click(within(form).getByRole('button', { name: 'Create goal' }))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('You can have up to 50 savings goals'))
    expect(screen.getByRole('form', { name: 'New savings goal' })).toBeTruthy()               // stays open to fix it
  })

  it('stops offering new goals at the limit', async () => {
    client.fetchSavingsGoals.mockResolvedValue(LIST([goal(), goal({ id: 2 })], { limit: 2 }))
    show()
    await screen.findAllByText('Trip')
    expect(screen.getByRole('button', { name: '➕ New goal' }).disabled).toBe(true)
    expect(screen.getByText('You’ve reached the limit of 2 goals.')).toBeTruthy()
  })

  it('keeps the list and says so when a refresh fails', async () => {
    client.fetchSavingsGoals.mockResolvedValueOnce(LIST([goal()]))
    client.addSavingsContribution.mockResolvedValue({ contributions: [] })
    show()
    await screen.findByText('Trip')
    fireEvent.click(screen.getByRole('button', { name: 'Add or take out money' }))
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '10' } })
    client.fetchSavingsGoals.mockRejectedValueOnce(new Error('offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByText(/Couldn’t refresh: offline/)
    expect(screen.getByText('Trip')).toBeTruthy()
  })
})

describe('a goal card', () => {
  async function card(g = goal(), props = {}) {
    client.fetchSavingsGoals.mockResolvedValue(LIST([g]))
    show(props)
    await screen.findByText(g.name)
    return screen.getByTestId(`goal-${g.id}`)
  }

  it('adds money, then reloads the list', async () => {
    const el = await card()
    client.addSavingsContribution.mockResolvedValue({ contributions: [] })
    fireEvent.click(within(el).getByRole('button', { name: 'Add or take out money' }))
    const form = within(el).getByRole('form', { name: 'Add money to Trip' })
    fireEvent.change(within(form).getByLabelText('Amount'), { target: { value: '250.50' } })
    fireEvent.change(within(form).getByLabelText('Date'), { target: { value: '2026-10-03' } })
    fireEvent.change(within(form).getByLabelText('Note'), { target: { value: ' bonus ' } })
    client.fetchSavingsGoals.mockClear()
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(client.addSavingsContribution).toHaveBeenCalledWith(1, { amount: '250.50', note: 'bonus', date: '2026-10-03' }))
    await waitFor(() => expect(client.fetchSavingsGoals).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(within(el).queryByRole('form')).toBeNull())                        // the form closes
  })

  it('takes money out with a negative amount', async () => {
    const el = await card()
    client.addSavingsContribution.mockResolvedValue({ contributions: [] })
    fireEvent.click(within(el).getByRole('button', { name: 'Add or take out money' }))
    const form = within(el).getByRole('form', { name: 'Add money to Trip' })
    fireEvent.click(within(form).getByRole('button', { name: 'Take out', pressed: false }))
    fireEvent.change(within(form).getByLabelText('Amount'), { target: { value: '80' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(client.addSavingsContribution).toHaveBeenCalledWith(1, expect.objectContaining({ amount: '-80' })))
  })

  it('shows the date as today in the person’s calendar and caps it there', async () => {
    const el = await card()
    fireEvent.click(within(el).getByRole('button', { name: 'Add or take out money' }))
    const date = within(el).getByLabelText('Date')
    expect(date.value).toBe(todayLocal())
    expect(date.getAttribute('max')).toBe(todayLocal())
  })

  it('does not send an empty amount, and shows the server’s reason when it refuses', async () => {
    const el = await card()
    fireEvent.click(within(el).getByRole('button', { name: 'Add or take out money' }))
    const form = within(el).getByRole('form', { name: 'Add money to Trip' })
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
    expect((await within(el).findByRole('alert')).textContent).toBe('Enter an amount above zero.')
    expect(client.addSavingsContribution).not.toHaveBeenCalled()
    fireEvent.change(within(form).getByLabelText('Amount'), { target: { value: '99999' } })
    client.addSavingsContribution.mockRejectedValue(new Error('That would take out more than has been saved'))
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(within(el).getByRole('alert').textContent).toBe('That would take out more than has been saved'))
  })

  it('shows the history, newest first as the server sends it, and removes an entry', async () => {
    const el = await card()
    const rows = [{ id: 11, date: '2026-10-20', amount: 200, note: 'bonus' }, { id: 10, date: '2026-10-01', amount: -50, note: '' }]
    client.fetchSavingsGoal.mockResolvedValue({ ...goal(), contributions: rows })
    fireEvent.click(within(el).getByRole('button', { name: 'History (2)' }))
    await within(el).findByText('Added SEK 200.00 on 20 Oct 2026: bonus')
    expect(within(el).getByText('Withdrew SEK 50.00 on 1 Oct 2026')).toBeTruthy()
    client.deleteSavingsContribution.mockResolvedValue({ contributions: [rows[1]] })
    fireEvent.click(within(el).getByRole('button', { name: /Remove Added SEK\s200\.00 on 20 Oct 2026: bonus/ }))
    await waitFor(() => expect(client.deleteSavingsContribution).toHaveBeenCalledWith(1, 11))
    await waitFor(() => expect(within(el).queryByText('Added SEK 200.00 on 20 Oct 2026: bonus')).toBeNull())
  })

  it('says when nothing has been added, and shows an error when the history will not load', async () => {
    const el = await card(goal({ contribution_count: 0 }))
    client.fetchSavingsGoal.mockResolvedValueOnce({ ...goal(), contributions: [] })
    fireEvent.click(within(el).getByRole('button', { name: 'History (0)' }))
    await within(el).findByText('Nothing added yet.')
    fireEvent.click(within(el).getByRole('button', { name: 'History (0)' }))                      // closes
    expect(within(el).queryByText('Nothing added yet.')).toBeNull()
    client.fetchSavingsGoal.mockRejectedValueOnce(new Error('offline'))
    fireEvent.click(within(el).getByRole('button', { name: 'History (0)' }))
    await within(el).findByRole('alert')
    expect(within(el).getByRole('alert').textContent).toBe('offline')
  })

  it('edits a goal, with the date optional', async () => {
    const el = await card(goal({ contribution_count: 0, note: 'old' }))
    client.updateSavingsGoal.mockResolvedValue({})
    fireEvent.click(within(el).getByRole('button', { name: 'Edit' }))
    const form = within(el).getByRole('form', { name: 'Edit Trip' })
    expect(within(form).getByLabelText('Goal name').value).toBe('Trip')
    expect(within(form).getByLabelText('Target amount').value).toBe('10000')
    expect(within(form).getByLabelText('Target date').value).toBe('2027-03-05')
    expect(within(form).getByLabelText('Goal note').value).toBe('old')
    fireEvent.change(within(form).getByLabelText('Goal name'), { target: { value: 'Holiday' } })
    fireEvent.change(within(form).getByLabelText('Target date'), { target: { value: '' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(client.updateSavingsGoal).toHaveBeenCalledWith(1, {
      name: 'Holiday', target_amount: '10000', target_date: null, note: 'old', currency: 'SEK',
    }))
    await waitFor(() => expect(within(el).queryByRole('form')).toBeNull())
  })

  it('does not offer a currency change once money has been added', async () => {
    const el = await card(goal({ contribution_count: 3 }))
    client.updateSavingsGoal.mockResolvedValue({})
    fireEvent.click(within(el).getByRole('button', { name: 'Edit' }))
    const form = within(el).getByRole('form', { name: 'Edit Trip' })
    expect(within(form).getByTitle('The currency can’t change once money has been added').disabled).toBe(true)
    fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(client.updateSavingsGoal).toHaveBeenCalled())
    expect(client.updateSavingsGoal.mock.calls[0][1].currency).toBeUndefined()
  })

  it('asks before deleting, and only deletes on yes', async () => {
    const el = await card()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    client.deleteSavingsGoal.mockResolvedValue(null)
    fireEvent.click(within(el).getByRole('button', { name: 'Delete' }))
    expect(confirm).toHaveBeenLastCalledWith('Delete “Trip” and its 2 deposits and withdrawals?')
    expect(client.deleteSavingsGoal).not.toHaveBeenCalled()
    client.fetchSavingsGoals.mockResolvedValue(LIST([]))
    fireEvent.click(within(el).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(client.deleteSavingsGoal).toHaveBeenCalledWith(1))
    await waitFor(() => expect(screen.queryByText('Trip')).toBeNull())
  })

  it('words the delete question for a goal with nothing in it', async () => {
    const el = await card(goal({ contribution_count: 0 }))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(within(el).getByRole('button', { name: 'Delete' }))
    expect(confirm).toHaveBeenLastCalledWith('Delete “Trip”?')
    confirm.mockClear()
    const one = goal({ id: 3, name: 'Solo', contribution_count: 1 })
    client.fetchSavingsGoals.mockResolvedValue(LIST([one]))
  })

  it('keeps the goal and says why when deleting fails', async () => {
    const el = await card()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    client.deleteSavingsGoal.mockRejectedValue(new Error('Savings goal not found'))
    fireEvent.click(within(el).getByRole('button', { name: 'Delete' }))
    await within(el).findByRole('alert')
    expect(within(el).getByRole('alert').textContent).toBe('Savings goal not found')
    expect(screen.getByText('Trip')).toBeTruthy()
  })

  it('shows a reached goal as reached, with a full bar', async () => {
    const el = await card(goal({ status: 'reached', pct: 120, saved: 12000, remaining: 0, reached: true, days_left: 50 }))
    expect(within(el).getByText('Reached')).toBeTruthy()
    expect(within(el).getByText('You’ve reached this goal.')).toBeTruthy()
    expect(within(el).getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100')
    expect(within(el).queryByText(/days left/)).toBeNull()
  })

  it('shows the note, when there is one', async () => {
    const el = await card(goal({ note: 'for the summer' }))
    expect(within(el).getByText('for the summer')).toBeTruthy()
  })
})

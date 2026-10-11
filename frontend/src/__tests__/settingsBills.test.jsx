import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import SettingsPage from '../pages/SettingsPage.jsx'

const OPTIONS = {
  categories: [], subcategories: {}, units: [], shops: [], currencies: ['EUR', 'SEK'],
  base_currency: 'SEK', display_currency: 'SEK', display_currency_is_custom: false, count_bills_as_spending: true,
}

function renderSettings(options = OPTIONS) {
  const props = { user: { email: 'a@b.c', has_password: true }, options, onOptionsUpdated: vi.fn(), onError: vi.fn(), onDeleteAccount: vi.fn() }
  render(<SettingsPage {...props} />)
  fireEvent.click(screen.getByRole('button', { name: /data/i }))
  return props
}

beforeEach(() => vi.clearAllMocks())

describe('Settings: bills', () => {
  it('shows the spending switch, on by default', () => {
    renderSettings()
    expect(screen.getByRole('heading', { name: 'Bills' })).toBeTruthy()
    expect(screen.getByRole('switch', { name: /Count new bills as spending right away/ }).checked).toBe(true)
  })

  it('also reflects it being off', () => {
    renderSettings({ ...OPTIONS, count_bills_as_spending: false })
    expect(screen.getByRole('switch', { name: /Count new bills/ }).checked).toBe(false)
  })

  it('saves the change and hands the new options to the app', async () => {
    client.saveCountBillsAsSpending.mockResolvedValueOnce({ ...OPTIONS, count_bills_as_spending: false })
    const props = renderSettings()
    fireEvent.click(screen.getByRole('switch', { name: /Count new bills/ }))
    await waitFor(() => expect(props.onOptionsUpdated).toHaveBeenCalled())
    expect(client.saveCountBillsAsSpending).toHaveBeenCalledWith(false)
    expect(props.onOptionsUpdated.mock.calls[0][0].count_bills_as_spending).toBe(false)
  })

  it('reports a failed save', async () => {
    client.saveCountBillsAsSpending.mockRejectedValueOnce(new Error('Not allowed'))
    const props = renderSettings()
    fireEvent.click(screen.getByRole('switch', { name: /Count new bills/ }))
    await waitFor(() => expect(props.onError).toHaveBeenCalledWith('Not allowed'))
    expect(props.onOptionsUpdated).not.toHaveBeenCalled()
  })
})

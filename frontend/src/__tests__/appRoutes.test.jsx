import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const OPTIONS = {
  categories: [], subcategories: {}, units: [], shops: [], currencies: ['SEK'],
  base_currency: 'SEK', display_currency: 'SEK', display_currency_is_custom: false, count_bills_as_spending: true,
}

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  mocked.getToken = vi.fn(() => 'token')
  mocked.onSessionExpired = vi.fn(() => () => {})
  mocked.fetchMe = vi.fn(async () => ({ email: 'a@b.c', name: 'A', has_password: true }))
  mocked.fetchOptions = vi.fn(async () => OPTIONS)
  mocked.fetchExpenses = vi.fn(async () => ({ items: [], total: 0 }))
  mocked.fetchGroups = vi.fn(async () => [
    { id: 1, name: 'Household', role: 'owner', space_type: 'household', currency: 'SEK', member_count: 1 },
  ])
  mocked.fetchInvitations = vi.fn(async () => [{ id: 9, group_id: 3, group_name: 'Cabin', role: 'editor', invited_by: 'Sam' }])
  return mocked
})

import App from '../App.jsx'

beforeEach(() => vi.clearAllMocks())

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('routes after the restructure', () => {
  it('sends the old /groups address to the Spaces tab in Settings', async () => {
    renderAt('/groups')
    expect(await screen.findByRole('heading', { name: /New Expense Space/ })).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: /Settings/ })).toBeTruthy()
  })

  it('shows the waiting-invitation badge on Settings in the sidebar', async () => {
    renderAt('/')
    expect(await screen.findByRole('status', { name: '1 invitation waiting' })).toBeTruthy()
  })

  it('has no Expense Spaces entry in the sidebar', async () => {
    renderAt('/')
    await waitFor(() => expect(screen.getByRole('link', { name: /Settings/ })).toBeTruthy())
    expect(screen.queryByRole('link', { name: /Expense Spaces/ })).toBeNull()
  })
})

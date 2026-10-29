import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import * as client from '../api/client.js'
import Layout from '../Layout.jsx'
import SettingsPage from '../pages/SettingsPage.jsx'

const OPTIONS = {
  categories: [], subcategories: {}, units: [], shops: [], currencies: ['EUR', 'SEK'],
  base_currency: 'SEK', display_currency: 'SEK', display_currency_is_custom: false, count_bills_as_spending: true,
}

function renderLayout(props = {}, entry = '/') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Layout
        user={{ name: 'A', email: 'a@b.com' }}
        onLogout={vi.fn()}
        error={null}
        loading={false}
        alerts={[]}
        options={{ display_currency: 'SEK', currencies: ['SEK'] }}
        onDisplayCurrencyChange={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())

describe('sidebar', () => {
  it('is grouped, with Expense Spaces moved into Settings and Prices and Shops into Insights', () => {
    renderLayout()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    const titles = [...nav.querySelectorAll('.nav-group-title')].map((n) => n.textContent)
    expect(titles).toEqual(['Money'])
    const labels = within(nav).getAllByRole('link').map((l) => l.textContent.replace(l.querySelector('.nav-icon').textContent, '').trim())
    expect(labels).toEqual(['Dashboard', 'Spending', 'Income', 'Recurring', 'Savings', 'Import', 'Insights', 'Trips', 'Settings'])
    expect(screen.queryByRole('link', { name: /Expense Spaces/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /Prices/ })).toBeNull()
    expect(screen.queryByRole('link', { name: /Bills/ })).toBeNull()
    expect(screen.getByRole('link', { name: /Spending/ }).getAttribute('href')).toBe('/spending')
    expect(screen.queryByRole('link', { name: /Shops/ })).toBeNull()
    expect(screen.getByRole('link', { name: /Insights/ }).getAttribute('href')).toBe('/insights')
    expect(screen.getByRole('link', { name: /Savings/ }).getAttribute('href')).toBe('/savings')
  })

  it('shows a badge on Settings with the number of invitations waiting', () => {
    renderLayout({ invitationCount: 2 })
    expect(screen.getByRole('status', { name: '2 invitations waiting' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Settings/ }).textContent).toMatch(/2/)
  })

  it('says "1 invitation" in the singular', () => {
    renderLayout({ invitationCount: 1 })
    expect(screen.getByRole('status', { name: '1 invitation waiting' })).toBeTruthy()
  })

  it('shows no badge when nothing is waiting', () => {
    renderLayout({ invitationCount: 0 })
    expect(screen.queryByRole('status')).toBeNull()
  })
})

const SPACES = {
  groups: [{ id: 1, name: 'Home', role: 'owner', space_type: 'household', currency: 'SEK', member_count: 1 }],
  currencies: ['SEK'],
  baseCurrency: 'SEK',
  onCreateGroup: vi.fn(),
  onDeleteGroup: vi.fn(),
  onLeaveGroup: vi.fn(),
  onRefresh: vi.fn(),
  onInvitationsChange: vi.fn(),
}

function renderSettings(extra = {}) {
  const props = {
    user: { email: 'a@b.c', has_password: true }, options: OPTIONS, onOptionsUpdated: vi.fn(),
    onError: vi.fn(), onDeleteAccount: vi.fn(), onExport: vi.fn(), spaces: SPACES, ...extra,
  }
  render(<SettingsPage {...props} />)
  return props
}

describe('Settings: spaces and export', () => {
  it('has a Spaces & sharing tab that lists the spaces and creates new ones', () => {
    renderSettings()
    expect(screen.queryByRole('heading', { name: /New Expense Space/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Spaces & sharing/ }))
    expect(screen.getByRole('heading', { name: /New Expense Space/ })).toBeTruthy()
    expect(screen.getAllByText(/Home/).length).toBeGreaterThan(0)
    // the page title belongs to Settings, not to the embedded spaces page
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  it('opens on the Spaces tab when asked to (the old /groups address)', () => {
    renderSettings({ initialTab: 'spaces' })
    expect(screen.getByRole('heading', { name: /New Expense Space/ })).toBeTruthy()
  })

  it('ignores an unknown tab name', () => {
    renderSettings({ initialTab: 'nonsense' })
    expect(screen.getByRole('heading', { name: 'Change password' })).toBeTruthy()
  })

  it('reports how many invitations are waiting to the sidebar', async () => {
    client.fetchInvitations.mockResolvedValue([
      { id: 1, group_id: 3, group_name: 'Home', role: 'editor', invited_by: 'Alex' },
      { id: 2, group_id: 4, group_name: 'Trip', role: 'viewer', invited_by: 'Sam' },
    ])
    renderSettings({ initialTab: 'spaces' })
    await waitFor(() => expect(SPACES.onInvitationsChange).toHaveBeenCalledWith(2))
  })

  it('offers Export under App data, calling the export handler', () => {
    const props = renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /App data/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
    expect(props.onExport.mock.calls).toEqual([['csv'], ['xlsx']])
  })

  it('hides the spaces tab when no spaces are wired in', () => {
    renderSettings({ spaces: undefined })
    expect(screen.queryByRole('button', { name: /Spaces & sharing/ })).toBeNull()
  })
})

describe('Insights sub-links', () => {
  const group = () => screen.queryByRole('group', { name: 'Insights sections' })

  it('are hidden away from Insights', () => {
    renderLayout({}, '/spending')
    expect(group()).toBeNull()
  })

  it('list every tab on Insights and mark the Overview by default', () => {
    renderLayout({}, '/insights')
    const links = within(group()).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(['Overview', 'Forecast', 'Categories', 'Report', 'Members', 'Shops', 'Prices'])
    expect(links[3].getAttribute('href')).toBe('/insights?tab=report')
    expect(links[0].getAttribute('aria-current')).toBe('page')
    expect(links.filter((l) => l.getAttribute('aria-current') === 'page')).toHaveLength(1)
  })

  it('mark the tab named in the address, and fall back to Overview for an unknown one', () => {
    const { unmount } = renderLayout({}, '/insights?tab=shops')
    expect(within(group()).getByRole('link', { name: 'Shops' }).getAttribute('aria-current')).toBe('page')
    expect(within(group()).getByRole('link', { name: 'Overview' }).getAttribute('aria-current')).toBeNull()
    unmount()
    renderLayout({}, '/insights?tab=nonsense')
    expect(within(group()).getByRole('link', { name: 'Overview' }).getAttribute('aria-current')).toBe('page')
  })

  it('move the mark when one is clicked', () => {
    renderLayout({}, '/insights')
    fireEvent.click(within(group()).getByRole('link', { name: 'Members' }))
    expect(within(group()).getByRole('link', { name: 'Members' }).getAttribute('aria-current')).toBe('page')
    expect(within(group()).getByRole('link', { name: 'Overview' }).getAttribute('aria-current')).toBeNull()
  })
})

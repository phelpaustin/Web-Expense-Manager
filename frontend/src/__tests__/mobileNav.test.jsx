import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import Layout from '../Layout.jsx'

let where
function Where() {
  where = useLocation()
  return null
}

// A matchMedia whose answer the test controls, and which can announce a change.
let phone
let listeners
function mockMatchMedia() {
  listeners = new Set()
  window.matchMedia = vi.fn(() => ({
    get matches() {
      return phone
    },
    addEventListener: (_t, fn) => listeners.add(fn),
    removeEventListener: (_t, fn) => listeners.delete(fn),
  }))
}

let onLogout, onUploadReceipt
function renderApp({ path = '/', invitationCount = 0 } = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Where />
      <Routes>
        <Route
          element={
            <Layout
              user={{ name: 'Ada', email: 'ada@example.com' }}
              onLogout={onLogout}
              error={null}
              loading={false}
              alerts={[]}
              options={{ display_currency: 'SEK', currencies: ['SEK'] }}
              onDisplayCurrencyChange={vi.fn()}
              invitationCount={invitationCount}
              onUploadReceipt={onUploadReceipt}
            />
          }
        >
          <Route path="*" element={<p>page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}
const bar = () => screen.getByRole('navigation', { name: 'Main' })
const openAdd = () => fireEvent.click(screen.getByRole('button', { name: 'Add' }))
const openMore = () => fireEvent.click(screen.getByRole('button', { name: /More/ }))

beforeEach(() => {
  phone = true
  onLogout = vi.fn()
  onUploadReceipt = vi.fn(async () => {})
  mockMatchMedia()
})
afterEach(() => {
  delete window.matchMedia
})

describe('phone navigation', () => {
  it('shows the sidebar on a wide screen and no bottom bar', () => {
    phone = false
    renderApp()
    expect(screen.getByRole('link', { name: /Income/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Add' })).toBeNull()
    expect(screen.queryByText('Log out')).toBeTruthy() // the sidebar footer
  })

  it('works where matchMedia does not exist', () => {
    delete window.matchMedia
    renderApp()
    expect(screen.getByRole('link', { name: /Income/ })).toBeTruthy()
  })

  it('shows a bottom bar instead of the sidebar on a phone', () => {
    renderApp()
    const links = within(bar()).getAllByRole('link').map((l) => l.textContent.replace(/[^A-Za-z]/g, ''))
    expect(links).toEqual(['Dashboard', 'Spending', 'Insights'])
    expect(within(bar()).getByRole('button', { name: 'Add' })).toBeTruthy()
    expect(within(bar()).getByRole('button', { name: /More/ })).toBeTruthy()
    expect(screen.queryByRole('link', { name: /Income/ })).toBeNull() // only in More
    expect(screen.getByText(/Expenses/)).toBeTruthy() // the brand moves to the top bar
  })

  it('marks the page you are on', () => {
    renderApp({ path: '/spending' })
    expect(within(bar()).getByRole('link', { name: /Spending/ }).className).toContain('active')
    expect(within(bar()).getByRole('link', { name: /Dashboard/ }).className).not.toContain('active')
  })

  it('follows the screen when it changes size', () => {
    phone = false
    renderApp()
    expect(screen.queryByRole('button', { name: 'Add' })).toBeNull()
    phone = true
    act(() => listeners.forEach((fn) => fn()))
    expect(screen.getByRole('button', { name: 'Add' })).toBeTruthy()
  })

  describe('Add sheet', () => {
    it('opens with three ways to add, and the button turns into Close', () => {
      renderApp()
      openAdd()
      const dialog = screen.getByRole('dialog', { name: 'Add' })
      expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual([
        expect.stringContaining('Add expense'),
        expect.stringContaining('Add a bill with items'),
        expect.stringContaining('Upload a receipt'),
        'Cancel',
      ])
      expect(screen.getByRole('button', { name: 'Close add menu' }).getAttribute('aria-expanded')).toBe('true')
    })

    it('Add expense opens Spending, All items', () => {
      renderApp()
      openAdd()
      fireEvent.click(screen.getByRole('button', { name: /Add expense/ }))
      expect(where.pathname + where.search).toBe('/spending?view=items')
      expect(screen.queryByRole('dialog')).toBeNull()
    })

    it('Add a bill with items opens the bill form', () => {
      renderApp()
      openAdd()
      fireEvent.click(screen.getByRole('button', { name: /Add a bill with items/ }))
      expect(where.pathname + where.search).toBe('/spending?view=items&add=bill')
    })

    it('Upload a receipt sends the file and shows By receipt', async () => {
      renderApp({ path: '/income' })
      openAdd()
      const file = new File(['x'], 'r.pdf', { type: 'application/pdf' })
      fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [file] } })
      await waitFor(() => expect(onUploadReceipt).toHaveBeenCalledWith(file))
      expect(where.pathname + where.search).toBe('/spending?view=receipts')
      expect(screen.queryByRole('dialog')).toBeNull()
    })

    it('choosing no file does nothing', () => {
      renderApp()
      openAdd()
      fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [] } })
      expect(onUploadReceipt).not.toHaveBeenCalled()
      expect(where.pathname).toBe('/')
    })

    it('closes on Cancel, Escape, the backdrop and the Close button', () => {
      renderApp()
      for (const close of [
        () => fireEvent.click(screen.getByRole('button', { name: 'Cancel' })),
        () => fireEvent.keyDown(document, { key: 'Escape' }),
        () => fireEvent.click(document.querySelector('.sheet-backdrop')),
        () => fireEvent.click(screen.getByRole('button', { name: 'Close add menu' })),
      ]) {
        openAdd()
        expect(screen.getByRole('dialog', { name: 'Add' })).toBeTruthy()
        close()
        expect(screen.queryByRole('dialog')).toBeNull()
      }
      expect(where.pathname).toBe('/')
    })

    it('moves focus into the sheet and back to the button when it closes', () => {
      renderApp()
      openAdd()
      expect(document.activeElement.textContent).toContain('Add expense')
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(document.activeElement.getAttribute('aria-label')).toBe('Add')
    })
  })

  describe('More sheet', () => {
    it('lists the other pages and goes to one, closing the sheet', () => {
      renderApp()
      openMore()
      const dialog = screen.getByRole('dialog', { name: 'More' })
      expect(within(dialog).getAllByRole('link').map((l) => l.textContent.replace(/[^A-Za-z]/g, ''))).toEqual([
        'Income', 'Recurring', 'Savings', 'Import', 'Trips', 'Settings',
      ])
      fireEvent.click(within(dialog).getByRole('link', { name: /Recurring/ }))
      expect(where.pathname).toBe('/recurring')
      expect(screen.queryByRole('dialog')).toBeNull()
    })

    it('has Log out and your name', () => {
      renderApp()
      openMore()
      expect(screen.getByText('Ada')).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
      expect(onLogout).toHaveBeenCalled()
    })

    it('shows waiting invitations on More and on Settings', () => {
      renderApp({ invitationCount: 2 })
      expect(bar().querySelector('.bottom-dot')).toBeTruthy()
      openMore()
      expect(screen.getByRole('status', { name: '2 invitations waiting' })).toBeTruthy()
    })

    it('is marked as the current place on a page that lives in it', () => {
      renderApp({ path: '/income' })
      expect(within(bar()).getByRole('button', { name: /More/ }).className).toContain('active')
    })

    it('switching from Add to More replaces the sheet', () => {
      renderApp()
      openAdd()
      openMore()
      expect(screen.queryByRole('dialog', { name: 'Add' })).toBeNull()
      expect(screen.getByRole('dialog', { name: 'More' })).toBeTruthy()
    })
  })
})

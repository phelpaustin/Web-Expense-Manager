import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

// The two views are covered by their own tests; here they are stubs so only the wrapper is under test.
vi.mock('../pages/BillsPage.jsx', () => ({
  default: ({ embedded }) => <div>RECEIPTS view{embedded ? ' (embedded)' : ''}</div>,
}))
vi.mock('../pages/ExpensesPage.jsx', () => ({
  default: ({ embedded, initialBillMode }) => (
    <div>ITEMS view{embedded ? ' (embedded)' : ''}{initialBillMode ? ' (bill mode)' : ''}</div>
  ),
}))

import SpendingPage from '../pages/SpendingPage.jsx'

const SLOW = { timeout: 5000 }
let where
function Where() {
  where = useLocation()
  return null
}

let bills
function renderAt(url) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Where />
      <SpendingPage bills={bills} expenseProps={{ options: { categories: [] } }} />
    </MemoryRouter>,
  )
}
const pressed = (name) => screen.getByRole('button', { name }).getAttribute('aria-pressed')

beforeEach(() => {
  localStorage.clear()
  bills = { reload: vi.fn(), actions: { uploadBill: vi.fn(async () => {}) } }
})

describe('SpendingPage', () => {
  it('opens on By receipt, under a single Spending title', async () => {
    renderAt('/spending')
    expect(await screen.findByText(/RECEIPTS view \(embedded\)/, {}, SLOW)).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: /Spending/ })).toBeTruthy()
    expect(pressed('By receipt')).toBe('true')
    expect(pressed('All items')).toBe('false')
  })

  it('shows All items for ?view=items', async () => {
    renderAt('/spending?view=items')
    expect(await screen.findByText(/ITEMS view \(embedded\)/, {}, SLOW)).toBeTruthy()
    expect(screen.queryByText(/RECEIPTS view/)).toBeNull()
    expect(pressed('All items')).toBe('true')
  })

  it('switching view updates the address and remembers the choice', async () => {
    renderAt('/spending')
    await screen.findByText(/RECEIPTS view/, {}, SLOW)
    fireEvent.click(screen.getByRole('button', { name: 'All items' }))
    expect(await screen.findByText(/ITEMS view/, {}, SLOW)).toBeTruthy()
    expect(where.search).toBe('?view=items')
    expect(localStorage.getItem('spendingView')).toBe('items')
  })

  it('opens on the remembered view when the address does not say', async () => {
    localStorage.setItem('spendingView', 'items')
    renderAt('/spending')
    expect(await screen.findByText(/ITEMS view/, {}, SLOW)).toBeTruthy()
  })

  it('an explicit view in the address wins over the remembered one', async () => {
    localStorage.setItem('spendingView', 'items')
    renderAt('/spending?view=receipts')
    expect(await screen.findByText(/RECEIPTS view/, {}, SLOW)).toBeTruthy()
  })

  it('reads the bills again when you come back to By receipt, but not on first load', async () => {
    renderAt('/spending?view=items')
    await screen.findByText(/ITEMS view/, {}, SLOW)
    expect(bills.reload).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'By receipt' }))
    await screen.findByText(/RECEIPTS view/, {}, SLOW)
    expect(bills.reload).toHaveBeenCalledTimes(1)
  })

  it('still works when browser storage is blocked', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    try {
      renderAt('/spending')
      await screen.findByText(/RECEIPTS view/, {}, SLOW)
      fireEvent.click(screen.getByRole('button', { name: 'All items' }))
      expect(await screen.findByText(/ITEMS view/, {}, SLOW)).toBeTruthy()
    } finally {
      get.mockRestore()
      set.mockRestore()
    }
  })

  describe('Add menu', () => {
    const open = () => fireEvent.click(screen.getByRole('button', { name: /Add/ }))

    it('lists the three ways to add and closes on Escape', async () => {
      renderAt('/spending')
      await screen.findByText(/RECEIPTS view/, {}, SLOW)
      expect(screen.queryByRole('menu')).toBeNull()
      open()
      expect(screen.getAllByRole('menuitem').map((m) => m.textContent)).toEqual([
        expect.stringContaining('Add expense'),
        expect.stringContaining('Add a bill with items'),
        expect.stringContaining('Upload a receipt'),
      ])
      fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
      expect(screen.queryByRole('menu')).toBeNull()
    })

    it('Add expense goes to All items', async () => {
      renderAt('/spending')
      await screen.findByText(/RECEIPTS view/, {}, SLOW)
      open()
      fireEvent.click(screen.getByRole('menuitem', { name: /Add expense/ }))
      expect(await screen.findByText(/ITEMS view/, {}, SLOW)).toBeTruthy()
      expect(screen.queryByText(/bill mode/)).toBeNull()
      expect(screen.queryByRole('menu')).toBeNull()
    })

    it('Add a bill with items opens All items in bill mode', async () => {
      renderAt('/spending')
      await screen.findByText(/RECEIPTS view/, {}, SLOW)
      open()
      fireEvent.click(screen.getByRole('menuitem', { name: /Add a bill with items/ }))
      expect(await screen.findByText(/ITEMS view \(embedded\) \(bill mode\)/, {}, SLOW)).toBeTruthy()
      expect(where.search).toContain('add=bill')
    })

    it('Upload a receipt sends the file and shows By receipt', async () => {
      renderAt('/spending?view=items')
      await screen.findByText(/ITEMS view/, {}, SLOW)
      const file = new File(['x'], 'r.pdf', { type: 'application/pdf' })
      fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [file] } })
      await waitFor(() => expect(bills.actions.uploadBill).toHaveBeenCalledWith(file))
      expect(await screen.findByText(/RECEIPTS view/, {}, SLOW)).toBeTruthy()
    })

    it('choosing no file does nothing', async () => {
      renderAt('/spending')
      await screen.findByText(/RECEIPTS view/, {}, SLOW)
      fireEvent.change(screen.getByLabelText('Receipt file'), { target: { files: [] } })
      expect(bills.actions.uploadBill).not.toHaveBeenCalled()
    })
  })
})

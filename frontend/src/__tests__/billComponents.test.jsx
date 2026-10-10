import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Pagination from '../components/Pagination.jsx'
import { BillStatusChip, TotalOnlyBadge } from '../components/BillStatus.jsx'

describe('Pagination', () => {
  const setup = (props = {}) => {
    const handlers = { onPage: vi.fn(), onPageSize: vi.fn() }
    render(<Pagination page={2} pageSize={25} total={312} {...handlers} {...props} />)
    return handlers
  }

  it('shows the visible range and page count', () => {
    setup()
    expect(screen.getByText('Showing 26–50 of 312')).toBeTruthy()
    expect(screen.getByText('Page 2 of 13')).toBeTruthy()
  })

  it('caps the range on the last page', () => {
    setup({ page: 13 })
    expect(screen.getByText('Showing 301–312 of 312')).toBeTruthy()
  })

  it('moves between pages and disables the ends', () => {
    const { onPage } = setup()
    fireEvent.click(screen.getByRole('button', { name: /Prev/ }))
    expect(onPage).toHaveBeenLastCalledWith(1)
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(onPage).toHaveBeenLastCalledWith(3)
  })

  it('disables Prev on the first page and Next on the last', () => {
    const { rerender } = render(<Pagination page={1} pageSize={25} total={30} onPage={() => {}} onPageSize={() => {}} />)
    expect(screen.getByRole('button', { name: /Prev/ }).disabled).toBe(true)
    rerender(<Pagination page={2} pageSize={25} total={30} onPage={() => {}} onPageSize={() => {}} />)
    expect(screen.getByRole('button', { name: /Next/ }).disabled).toBe(true)
  })

  it('changes the page size', () => {
    const { onPageSize } = setup()
    fireEvent.change(screen.getByLabelText('Rows per page'), { target: { value: '100' } })
    expect(onPageSize).toHaveBeenCalledWith(100)
  })

  it('renders nothing when there are no rows', () => {
    const { container } = render(<Pagination page={1} pageSize={25} total={0} onPage={() => {}} onPageSize={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('clamps an out-of-range page', () => {
    setup({ page: 99, total: 30 })
    expect(screen.getByText('Page 2 of 2')).toBeTruthy()
  })
})

describe('BillStatusChip', () => {
  it.each([
    ['pending', 'To itemise'],
    ['total_only', 'Total only'],
    ['itemised', 'Itemised'],
  ])('labels %s', (status, label) => {
    render(<BillStatusChip status={status} />)
    expect(screen.getByText(label).className).toContain(`status-${status}`)
  })

  it('shows the item count for itemised bills, singular and plural', () => {
    const { rerender } = render(<BillStatusChip status="itemised" itemCount={1} />)
    expect(screen.getByText('Itemised · 1 item')).toBeTruthy()
    rerender(<BillStatusChip status="itemised" itemCount={4} />)
    expect(screen.getByText('Itemised · 4 items')).toBeTruthy()
  })

  it('explains each state on hover', () => {
    render(<BillStatusChip status="total_only" />)
    expect(screen.getByText('Total only').title).toMatch(/itemise it any time/i)
  })
})

describe('TotalOnlyBadge', () => {
  it('marks an expense that is only a bill total', () => {
    render(<TotalOnlyBadge />)
    const badge = screen.getByText(/Total only/)
    expect(badge.className).toContain('total-only-badge')
    expect(badge.title).toMatch(/Itemise/)
  })
})

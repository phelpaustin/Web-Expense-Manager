import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CurrencySelect from '../components/CurrencySelect.jsx'

const LIST = ['EUR', 'SEK', 'USD']

describe('CurrencySelect', () => {
  it('offers a default option that names what the default resolves to', () => {
    render(<CurrencySelect value="" onChange={() => {}} currencies={LIST} defaultCurrency="SEK" />)
    expect(screen.getByRole('option', { name: 'Default (SEK)' })).toBeTruthy()
  })

  it('supports a custom default label and no default option at all', () => {
    const { rerender } = render(
      <CurrencySelect value="" onChange={() => {}} currencies={LIST} defaultLabel="Same as base currency" defaultCurrency="EUR" />,
    )
    expect(screen.getByRole('option', { name: 'Same as base currency (EUR)' })).toBeTruthy()
    rerender(<CurrencySelect value="EUR" onChange={() => {}} currencies={LIST} allowDefault={false} />)
    expect(screen.queryByRole('option', { name: /Default/ })).toBeNull()
  })

  it('keeps an unsupported legacy currency selectable so it can be edited away', () => {
    render(<CurrencySelect value="XXX" onChange={() => {}} currencies={LIST} allowDefault={false} />)
    expect(screen.getByRole('combobox').value).toBe('XXX')
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['XXX', 'EUR', 'SEK', 'USD'])
  })

  it('reports the chosen code, and "" for the default', () => {
    const onChange = vi.fn()
    render(<CurrencySelect value="USD" onChange={onChange} currencies={LIST} defaultCurrency="SEK" />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'EUR' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } })
    expect(onChange.mock.calls).toEqual([['EUR'], ['']])
  })

  it('renders safely before the currency list has loaded', () => {
    render(<CurrencySelect value="" onChange={() => {}} defaultCurrency="SEK" />)
    expect(screen.getAllByRole('option')).toHaveLength(1)
  })
})

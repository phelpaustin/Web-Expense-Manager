import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import UnitSelect, { unitChoices, COMMON_UNITS } from '../components/UnitSelect.jsx'

describe('unitChoices', () => {
  it("lists the user's units first, then common ones, without duplicates", () => {
    const out = unitChoices(['Kg', 'Bottle'])
    expect(out.slice(0, 2)).toEqual(['Kg', 'Bottle'])
    expect(out.filter((u) => u.toLowerCase() === 'kg')).toHaveLength(1)
    for (const u of COMMON_UNITS) expect(out).toContain(u)
  })

  it('keeps an unknown current value selectable (e.g. from an import)', () => {
    expect(unitChoices(['Count'], 'Crate')).toContain('Crate')
  })
})

describe('UnitSelect', () => {
  it('is a labelled dropdown that reports the choice', () => {
    const onChange = vi.fn()
    render(<UnitSelect value="Count" units={['Count', 'Kg']} onChange={onChange} />)
    const select = screen.getByRole('combobox', { name: 'Unit' })
    expect(select.value).toBe('Count')
    expect([...select.options].map((o) => o.value)).toEqual(expect.arrayContaining(['Count', 'Kg', 'Litre', 'Pack']))
    fireEvent.change(select, { target: { value: 'Litre' } })
    expect(onChange).toHaveBeenCalledWith('Litre')
  })

  it('falls back to Count when empty', () => {
    render(<UnitSelect value="" units={[]} onChange={() => {}} />)
    expect(screen.getByRole('combobox', { name: 'Unit' }).value).toBe('Count')
  })
})

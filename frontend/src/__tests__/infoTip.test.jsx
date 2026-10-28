import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import InfoTip from '../components/InfoTip.jsx'

const setup = () =>
  render(
    <div>
      <p>elsewhere</p>
      <InfoTip label="Why?">The explanation.</InfoTip>
    </div>,
  )
const button = () => screen.getByRole('button', { name: 'Why?' })

describe('InfoTip', () => {
  it('shows nothing until you hover or click', () => {
    setup()
    expect(screen.queryByText('The explanation.')).toBeNull()
    expect(button().getAttribute('aria-expanded')).toBe('false')
  })

  it('shows the note while hovering and hides it when the pointer leaves', () => {
    setup()
    fireEvent.mouseEnter(button().parentElement)
    expect(screen.getByRole('tooltip').textContent).toBe('The explanation.')
    expect(button().getAttribute('aria-describedby')).toBe(screen.getByRole('tooltip').id)
    fireEvent.mouseLeave(button().parentElement)
    expect(screen.queryByText('The explanation.')).toBeNull()
  })

  it('a click keeps it open after the pointer leaves, and another click closes it', () => {
    setup()
    const wrap = button().parentElement
    fireEvent.mouseEnter(wrap)
    fireEvent.click(button())
    fireEvent.mouseLeave(wrap)
    expect(screen.getByText('The explanation.')).toBeTruthy()
    expect(button().getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(button())
    expect(screen.queryByText('The explanation.')).toBeNull()
  })

  it('works with a click alone, as on a touch screen', () => {
    setup()
    fireEvent.click(button())
    expect(screen.getByText('The explanation.')).toBeTruthy()
  })

  it('closes on Escape', () => {
    setup()
    fireEvent.click(button())
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('The explanation.')).toBeNull()
  })

  it('closes when you press somewhere else, but not when you press inside it', () => {
    setup()
    fireEvent.click(button())
    fireEvent.pointerDown(screen.getByText('The explanation.'))
    expect(screen.getByText('The explanation.')).toBeTruthy()
    fireEvent.pointerDown(screen.getByText('elsewhere'))
    expect(screen.queryByText('The explanation.')).toBeNull()
  })
})

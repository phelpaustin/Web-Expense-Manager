import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PasswordInput from '../components/PasswordInput.jsx'

describe('PasswordInput', () => {
  it('hides the password by default and passes its props on', () => {
    render(<PasswordInput placeholder="Password" required minLength={12} defaultValue="secret" />)
    const input = screen.getByPlaceholderText('Password')
    expect(input.type).toBe('password')
    expect(input.required).toBe(true)
    expect(input.minLength).toBe(12)
  })

  it('shows and hides the password with the button, without submitting the form', () => {
    let submitted = false
    render(
      <form onSubmit={(e) => { e.preventDefault(); submitted = true }}>
        <PasswordInput placeholder="Password" defaultValue="secret" />
      </form>,
    )
    const input = screen.getByPlaceholderText('Password')
    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(input.type).toBe('text')
    expect(input.value).toBe('secret')
    const hide = screen.getByRole('button', { name: 'Hide password' })
    expect(hide.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(hide)
    expect(input.type).toBe('password')
    expect(submitted).toBe(false)
  })
})

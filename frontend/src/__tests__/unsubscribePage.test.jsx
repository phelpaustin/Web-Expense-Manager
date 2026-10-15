import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client.js', () => ({ unsubscribeDigest: vi.fn() }))
import { unsubscribeDigest } from '../api/client.js'
import UnsubscribePage from '../pages/UnsubscribePage.jsx'

const renderAt = (url) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <UnsubscribePage />
    </MemoryRouter>,
  )

describe('UnsubscribePage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does nothing until the button is clicked, then confirms', async () => {
    unsubscribeDigest.mockResolvedValue({})
    renderAt('/unsubscribe?token=abc')
    expect(unsubscribeDigest).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Unsubscribe' }))
    await waitFor(() => expect(screen.getByText(/You are unsubscribed/)).toBeTruthy())
    expect(unsubscribeDigest).toHaveBeenCalledWith('abc')
  })

  it('shows the error for an invalid link and allows retry', async () => {
    unsubscribeDigest.mockRejectedValue(new Error('This unsubscribe link is invalid or has expired.'))
    renderAt('/unsubscribe?token=bad')
    fireEvent.click(screen.getByRole('button', { name: 'Unsubscribe' }))
    await waitFor(() => expect(screen.getByText(/invalid or has expired/)).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Unsubscribe' })).toBeTruthy()
  })

  it('disables the button when the token is missing', () => {
    renderAt('/unsubscribe')
    expect(screen.getByRole('button', { name: 'Unsubscribe' }).disabled).toBe(true)
  })
})

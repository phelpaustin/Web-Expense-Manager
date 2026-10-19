import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import * as client from '../api/client.js'
import Invitations from '../components/Invitations.jsx'

const INVITE = { id: 7, group_id: 3, group_name: 'Home', role: 'editor', invited_by: 'Alex' }

beforeEach(() => {
  vi.clearAllMocks()
  client.fetchInvitations.mockResolvedValue([INVITE])
})

describe('Invitations', () => {
  it('shows who invited you to what, and nothing when there are none', async () => {
    render(<Invitations onAccepted={vi.fn()} onError={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Home')).toBeTruthy())
    expect(screen.getByText('Alex')).toBeTruthy()
    client.fetchInvitations.mockResolvedValue([])
    const empty = render(<Invitations onAccepted={vi.fn()} onError={vi.fn()} />)
    await waitFor(() => expect(client.fetchInvitations).toHaveBeenCalledTimes(2))
    expect(empty.container.textContent).toBe('')
  })

  it('accepting calls the API, removes the row and refreshes the spaces', async () => {
    const onAccepted = vi.fn(async () => {})
    render(<Invitations onAccepted={onAccepted} onError={vi.fn()} />)
    await waitFor(() => screen.getByText('Accept'))
    fireEvent.click(screen.getByText('Accept'))
    await waitFor(() => expect(client.acceptInvitation).toHaveBeenCalledWith(7))
    await waitFor(() => expect(screen.queryByText('Home')).toBeNull())
    expect(onAccepted).toHaveBeenCalled()
  })

  it('declining calls the API and does not refresh the spaces', async () => {
    const onAccepted = vi.fn()
    render(<Invitations onAccepted={onAccepted} onError={vi.fn()} />)
    await waitFor(() => screen.getByText('Decline'))
    fireEvent.click(screen.getByText('Decline'))
    await waitFor(() => expect(client.declineInvitation).toHaveBeenCalledWith(7))
    await waitFor(() => expect(screen.queryByText('Home')).toBeNull())
    expect(onAccepted).not.toHaveBeenCalled()
  })

  it('reports a failure and keeps the row', async () => {
    client.acceptInvitation.mockRejectedValue(new Error('nope'))
    const onError = vi.fn()
    render(<Invitations onAccepted={vi.fn()} onError={onError} />)
    await waitFor(() => screen.getByText('Accept'))
    fireEvent.click(screen.getByText('Accept'))
    await waitFor(() => expect(onError).toHaveBeenCalledWith('nope'))
    expect(screen.getByText('Home')).toBeTruthy()
  })
})

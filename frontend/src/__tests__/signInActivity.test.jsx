import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import SignInActivity from '../components/SignInActivity.jsx'
import * as client from '../api/client.js'

vi.mock('../api/client.js', () => ({ fetchSignIns: vi.fn() }))

const ok = { at: '2026-11-08T20:00:00+00:00', method: 'password', success: true, ip: '81.1.2.3', device: 'Chrome on Mac' }
const bad = { at: '2026-11-08T21:00:00+00:00', method: 'password', success: false, ip: '5.6.7.8', device: 'Script' }

describe('SignInActivity', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists sign-ins with device and address', async () => {
    client.fetchSignIns.mockResolvedValue({ events: [ok], failed_since_last_success: 0, keep_days: 180 })
    render(<SignInActivity />)
    expect(await screen.findByText('Chrome on Mac')).toBeTruthy()
    expect(screen.getByText('81.1.2.3')).toBeTruthy()
    expect(screen.getByText('Signed in')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('warns about failed attempts since the last successful sign-in', async () => {
    client.fetchSignIns.mockResolvedValue({ events: [bad, bad, ok], failed_since_last_success: 2, keep_days: 180 })
    render(<SignInActivity />)
    expect((await screen.findByRole('alert')).textContent).toContain('2 failed attempts')
    expect(screen.getAllByText('Wrong password')).toHaveLength(2)
  })

  it('says so when nothing is recorded yet', async () => {
    client.fetchSignIns.mockResolvedValue({ events: [], failed_since_last_success: 0, keep_days: 180 })
    render(<SignInActivity />)
    expect(await screen.findByText('Nothing recorded yet.')).toBeTruthy()
  })

  it('reports a failed load', async () => {
    client.fetchSignIns.mockRejectedValue(new Error('boom'))
    const onError = vi.fn()
    render(<SignInActivity onError={onError} />)
    await waitFor(() => expect(onError).toHaveBeenCalledWith('boom'))
  })
})

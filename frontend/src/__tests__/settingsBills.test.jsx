import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import * as client from '../api/client.js'
import SettingsPage from '../pages/SettingsPage.jsx'

const OPTIONS = {
  categories: [], subcategories: {}, units: [], shops: [], currencies: ['EUR', 'SEK'],
  base_currency: 'SEK', display_currency: 'SEK', display_currency_is_custom: false,
}

function renderSettings(options = OPTIONS) {
  const props = { user: { email: 'a@b.c', has_password: true }, options, onOptionsUpdated: vi.fn(), onError: vi.fn(), onDeleteAccount: vi.fn() }
  render(<SettingsPage {...props} />)
  fireEvent.click(screen.getByRole('button', { name: /data/i }))
  return props
}

beforeEach(() => vi.clearAllMocks())

describe('Settings: alert emails', () => {
  it('shows the switch (on by default) and reflects an opt-out', () => {
    renderSettings()
    expect(screen.getByRole('switch', { name: /Budget alert emails/ }).checked).toBe(true)
  })

  it('shows off when unsubscribed', () => {
    renderSettings({ ...OPTIONS, alert_digest_enabled: false })
    expect(screen.getByRole('switch', { name: /Budget alert emails/ }).checked).toBe(false)
  })

  it('saves the change', async () => {
    client.saveAlertDigest.mockResolvedValueOnce({ ...OPTIONS, alert_digest_enabled: false })
    const props = renderSettings()
    fireEvent.click(screen.getByRole('switch', { name: /Budget alert emails/ }))
    await waitFor(() => expect(props.onOptionsUpdated).toHaveBeenCalled())
    expect(client.saveAlertDigest).toHaveBeenCalledWith(false)
  })
})

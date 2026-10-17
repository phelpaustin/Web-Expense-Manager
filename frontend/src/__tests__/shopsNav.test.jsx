import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => ({}))
  return mocked
})

import Layout from '../Layout.jsx'

describe('navigation', () => {
  it('has a Shops link, next to Prices, that goes to /shops', () => {
    render(
      <MemoryRouter>
        <Layout user={{ name: 'A', email: 'a@b.com' }} onLogout={vi.fn()} error={null} loading={false} alerts={[]} options={{ display_currency: 'SEK', currencies: ['SEK'] }} onDisplayCurrencyChange={vi.fn()} />
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: /Shops/ })
    expect(link.getAttribute('href')).toBe('/shops')
    const labels = screen.getAllByRole('link').map((l) => l.textContent)
    expect(labels.findIndex((t) => /Shops/.test(t))).toBe(labels.findIndex((t) => /Prices/.test(t)) + 1)
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const server = { options: null }

vi.mock('../api/client.js', async (importOriginal) => {
  const actual = await importOriginal()
  const mocked = {}
  for (const k of Object.keys(actual)) mocked[k] = vi.fn(async () => [])
  return mocked
})

import * as client from '../api/client.js'
import { useAppData } from '../hooks/useAppData.js'
import Layout from '../Layout.jsx'
import SettingsPage from '../pages/SettingsPage.jsx'
import { money } from '../format.js'

const OPTIONS = {
  categories: [], subcategories: {}, units: [], shops: [],
  base_currency: 'SEK', display_currency: 'SEK', display_currency_is_custom: false,
  currencies: ['EUR', 'SEK', 'USD'],
}

beforeEach(() => {
  server.options = { ...OPTIONS }
  client.fetchOptions.mockImplementation(async () => ({ ...server.options }))
  client.fetchSummary.mockImplementation(async () => null)
  client.fetchTrends.mockImplementation(async () => null)
  client.fetchMetrics.mockImplementation(async () => null)
  client.fetchPeriodStatus.mockImplementation(async () => null)
  client.fetchIncomeSummary.mockImplementation(async () => null)
  client.fetchBudgetConfig.mockImplementation(async () => ({ period: 'Monthly', rollover: false }))
  client.saveDisplayCurrency.mockImplementation(async (code) => {
    server.options = { ...server.options, display_currency: code || server.options.base_currency, display_currency_is_custom: !!code }
    return { ...server.options }
  })
  client.setBaseCurrency.mockImplementation(async (code) => {
    server.options = {
      ...server.options, base_currency: code,
      display_currency: server.options.display_currency_is_custom ? server.options.display_currency : code,
    }
    return { ...server.options }
  })
})

describe('display currency switching', () => {
  it('useAppData.changeDisplayCurrency saves, updates options, formats money, and reloads', async () => {
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.loadAll() })
    expect(result.current.options.display_currency).toBe('SEK')
    const callsBefore = client.fetchSummary.mock.calls.length

    await act(async () => { await result.current.changeDisplayCurrency('EUR') })

    expect(client.saveDisplayCurrency).toHaveBeenCalledWith('EUR')
    expect(result.current.options.display_currency).toBe('EUR')
    expect(result.current.options.display_currency_is_custom).toBe(true)
    expect(money(10)).toContain('€')                       // money() now formats in the display currency
    expect(client.fetchSummary.mock.calls.length).toBeGreaterThan(callsBefore)  // converted views reloaded
    expect(result.current.error).toBeNull()

    await act(async () => { await result.current.changeDisplayCurrency(null) })   // reset -> follow base
    expect(client.saveDisplayCurrency).toHaveBeenLastCalledWith(null)
    expect(result.current.options.display_currency).toBe('SEK')
  })

  it('a failing save reports the error and does not crash', async () => {
    client.saveDisplayCurrency.mockRejectedValueOnce(new Error('Currency XXX is not supported'))
    const { result } = renderHook(() => useAppData())
    await act(async () => { await result.current.changeDisplayCurrency('XXX') })
    expect(result.current.error).toMatch(/not supported/)
  })

  it('the top-bar switcher shows the display currency and calls the handler', () => {
    const onChange = vi.fn()
    render(
      <MemoryRouter>
        <Layout user={{ email: 'a@b.c' }} onLogout={() => {}} options={{ ...OPTIONS, display_currency: 'USD' }} onDisplayCurrencyChange={onChange} />
      </MemoryRouter>,
    )
    const select = screen.getByTitle('Currency')
    expect(select.value).toBe('USD')
    fireEvent.change(select, { target: { value: 'EUR' } })
    expect(onChange).toHaveBeenCalledWith('EUR')
  })

  it('the switcher is hidden until the currency list has loaded', () => {
    render(
      <MemoryRouter>
        <Layout user={{ email: 'a@b.c' }} onLogout={() => {}} options={{ ...OPTIONS, currencies: [] }} onDisplayCurrencyChange={() => {}} />
      </MemoryRouter>,
    )
    expect(screen.queryByText(/View in/)).toBeNull()
  })
})

describe('Settings: base vs display currency', () => {
  function renderSettings(opts, extra = {}) {
    const props = {
      user: { email: 'a@b.c', has_password: true }, options: opts, onOptionsUpdated: vi.fn(),
      onCurrencyChanged: vi.fn(), onDisplayCurrencyChange: vi.fn(), onError: vi.fn(), onDeleteAccount: vi.fn(), ...extra,
    }
    render(<SettingsPage {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /data/i }))
    return props
  }

  it('shows two separate settings', () => {
    renderSettings(OPTIONS)
    expect(screen.getByRole('heading', { name: 'Base currency' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Display currency' })).toBeTruthy()
    expect(screen.getByTitle('Display currency').value).toBe('')          // "same as base"
    expect(screen.getByText(/Same as base currency \(SEK\)/)).toBeTruthy()
  })

  it('choosing a display currency calls the handler; "same as base" sends null/empty', () => {
    const props = renderSettings(OPTIONS)
    fireEvent.change(screen.getByTitle('Display currency'), { target: { value: 'USD' } })
    expect(props.onDisplayCurrencyChange).toHaveBeenCalledWith('USD')
  })

  it('changing base currency while display follows base reloads converted views', async () => {
    const props = renderSettings(OPTIONS)
    fireEvent.change(screen.getByTitle('Base currency'), { target: { value: 'EUR' } })
    await waitFor(() => expect(props.onOptionsUpdated).toHaveBeenCalled())
    expect(client.setBaseCurrency).toHaveBeenCalledWith('EUR')
    expect(props.onOptionsUpdated.mock.calls[0][0].base_currency).toBe('EUR')
    expect(props.onCurrencyChanged).toHaveBeenCalled()
  })

  it('changing base currency with a custom display currency does not reload', async () => {
    server.options = { ...OPTIONS, display_currency: 'USD', display_currency_is_custom: true }
    const props = renderSettings(server.options)
    fireEvent.change(screen.getByTitle('Base currency'), { target: { value: 'EUR' } })
    await waitFor(() => expect(props.onOptionsUpdated).toHaveBeenCalled())
    expect(props.onOptionsUpdated.mock.calls[0][0].display_currency).toBe('USD')
    expect(props.onCurrencyChanged).not.toHaveBeenCalled()
  })
})

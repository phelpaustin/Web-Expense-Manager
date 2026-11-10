import { useCallback, useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { createRecurring, fetchSubscriptions, ignoreSubscription, unignoreSubscription } from '../api/client.js'
import { dayLabel, headline, perText, priceChangeText, trackPayload } from '../subscriptions.js'

// "Subscriptions found": repeating charges in the expenses that are not set up as recurring payments,
// with what they cost, price rises and the ones that seem to have stopped. Each can be tracked as a
// recurring payment or marked "not a subscription".
export default function SubscriptionsPanel({ refreshKey, onTracked }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const latest = useRef(0)

  const load = useCallback(() => {
    const request = ++latest.current
    return fetchSubscriptions()
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  async function act(work) {
    setBusy(true)
    try {
      await work()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const track = (item) =>
    act(async () => {
      await createRecurring(trackPayload(item))
      onTracked?.()
    })

  if (error && !data) {
    return (
      <section className="panel">
        <h2>🔎 Subscriptions found</h2>
        <p className="subtitle">Couldn’t look for subscriptions: {error}</p>
      </section>
    )
  }
  if (!data || !Array.isArray(data.items)) {
    return (
      <section className="panel">
        <h2>🔎 Subscriptions found</h2>
        <p className="subtitle">Looking…</p>
      </section>
    )
  }

  const stopped = Array.isArray(data.stopped) ? data.stopped : []
  const ignored = Array.isArray(data.ignored) ? data.ignored : []

  return (
    <section className="panel subscriptions">
      <h2>🔎 Subscriptions found</h2>
      <p data-testid="subscriptions-headline">{headline(data)}</p>
      {error && <p className="auth-error" role="alert">{error}</p>}

      {data.items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Charge</th>
              <th className="right">Amount</th>
              <th className="right">Per month</th>
              <th>Last charged</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={`${i.key}|${i.currency}`}>
                <td>
                  {i.name}
                  <div className="subtitle">
                    {i.charges} charges since {dayLabel(i.first_date)}
                    {i.varies ? ' · amount varies' : ''}
                  </div>
                  {i.price_change && (
                    <div className={`subtitle ${i.price_change.direction === 'up' ? 'up' : 'down'}`}>{priceChangeText(i.price_change)}</div>
                  )}
                </td>
                <td className="right">
                  {money(i.amount, i.currency)} <span className="subtitle">{perText(i.frequency)}</span>
                </td>
                <td className="right">{i.monthly == null ? '—' : money(i.monthly, data.currency)}</td>
                <td>
                  {dayLabel(i.last_date)}
                  <div className="subtitle">next about {dayLabel(i.next_due)}</div>
                </td>
                <td className="right sub-actions">
                  <button type="button" className="mini-btn" disabled={busy} onClick={() => track(i)}>
                    Track as recurring
                  </button>{' '}
                  <button type="button" className="mini-btn" disabled={busy} onClick={() => act(() => ignoreSubscription(i.name))}>
                    Not a subscription
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data.unconverted_count > 0 && (
        <p className="subtitle">
          {data.unconverted_count} {data.unconverted_count === 1 ? 'charge' : 'charges'} in a currency without an exchange rate{' '}
          {data.unconverted_count === 1 ? 'is' : 'are'} left out of the totals.
        </p>
      )}

      {stopped.length > 0 && (
        <details>
          <summary>No longer charging ({stopped.length})</summary>
          <p className="subtitle">These repeated for a while and then stopped: cancelled, or worth a check.</p>
          <ul className="sub-list">
            {stopped.map((i) => (
              <li key={`${i.key}|${i.currency}`}>
                {i.name} · {money(i.amount, i.currency)} <span className="subtitle">{perText(i.frequency)}</span> · last charged{' '}
                {dayLabel(i.last_date)}{' '}
                <button type="button" className="mini-btn" disabled={busy} onClick={() => act(() => ignoreSubscription(i.name))}>
                  Not a subscription
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      {ignored.length > 0 && (
        <details>
          <summary>Marked not a subscription ({ignored.length})</summary>
          <ul className="sub-list">
            {ignored.map((i) => (
              <li key={i.key}>
                {i.name}{' '}
                <button type="button" className="mini-btn" disabled={busy} onClick={() => act(() => unignoreSubscription(i.name))}>
                  Show again
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {data.tracked_count > 0 && data.items.length > 0 && (
        <p className="subtitle">{data.tracked_count} more already in your recurring payments.</p>
      )}
    </section>
  )
}

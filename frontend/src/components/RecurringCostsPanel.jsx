import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { money } from '../format.js'
import { fetchRecurringCosts } from '../api/client.js'
import { dueText, headline, perText, priceChangeText } from '../recurringCosts.js'

// "What do my subscriptions cost?": every recurring payment as a cost per month and per year, when
// it is next due, and which ones have gone up in price.
export default function RecurringCostsPanel({ refreshKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)

  useEffect(() => {
    const request = ++latest.current
    fetchRecurringCosts()
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [refreshKey])

  if (error && !data) {
    return (
      <section className="panel">
        <h2>🔁 Recurring costs</h2>
        <p className="subtitle">Couldn’t load the recurring costs: {error}</p>
      </section>
    )
  }
  if (!data || !Array.isArray(data.items)) {
    return (
      <section className="panel">
        <h2>🔁 Recurring costs</h2>
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const rises = data.items.filter((i) => i.price_change && i.price_change.direction === 'up')

  return (
    <section className="panel">
      <div className="period-header">
        <h2>🔁 Recurring costs</h2>
        <Link to="/recurring">Manage recurring</Link>
      </div>
      <p data-testid="recurring-headline">{headline(data)}</p>

      {rises.length > 0 && (
        <p className="recurring-rises" role="status">
          {rises.length === 1 ? '1 price rise: ' : `${rises.length} price rises: `}
          {rises.map((i) => (i.price_change.pct_change == null ? i.item : `${i.item} +${i.price_change.pct_change}%`)).join(', ')}.
        </p>
      )}

      {data.items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Payment</th>
              <th className="right">Amount</th>
              <th className="right">Per month</th>
              <th>Next due</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={i.id}>
                <td>
                  {i.item}
                  {i.price_change && (
                    <div className={`subtitle ${i.price_change.direction === 'up' ? 'up' : 'down'}`}>{priceChangeText(i.price_change)}</div>
                  )}
                </td>
                <td className="right">
                  {money(i.native_amount, i.native_currency)} <span className="subtitle">{perText(i.frequency)}</span>
                </td>
                <td className="right">{money(i.monthly)}</td>
                <td className={i.overdue ? 'up' : ''}>{dueText(i)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data.unconverted_count > 0 && (
        <p className="subtitle">
          {data.unconverted_count} recurring {data.unconverted_count === 1 ? 'payment' : 'payments'} in a currency without an exchange rate{' '}
          {data.unconverted_count === 1 ? 'is' : 'are'} left out of the totals.
        </p>
      )}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </section>
  )
}

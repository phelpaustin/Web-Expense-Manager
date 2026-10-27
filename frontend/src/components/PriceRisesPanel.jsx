import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchPriceRises } from '../api/client.js'
import { WINDOWS, describeRise, isBigRise, riseName, summaryText } from '../priceRises.js'

// "What got more expensive?": items whose latest price, at the shop you bought them at, is well above
// what you usually paid there. The same product at the same shop is followed, so switching shop or
// brand is never mistaken for a rise. The biggest also appear in the bell.
export default function PriceRisesPanel({ refreshKey }) {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)

  useEffect(() => {
    const request = ++latest.current
    fetchPriceRises({ recentDays: days })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [days, refreshKey])

  const heading = (
    <div className="period-header">
      <h2>📈 Price rises</h2>
      <select aria-label="Price rises window" value={days} onChange={(e) => setDays(Number(e.target.value))}>
        {WINDOWS.map((w) => (
          <option key={w.days} value={w.days}>
            {w.label}
          </option>
        ))}
      </select>
    </div>
  )

  if (error && !data) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Couldn’t load the price rises: {error}</p>
      </section>
    )
  }
  if (!data || !Array.isArray(data.items)) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const note = summaryText(data)

  return (
    <section className="panel">
      {heading}
      {data.items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Shop</th>
              <th className="right">Now</th>
              <th className="right">Your usual</th>
              <th className="right">Rise</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={`${i.item}|${i.brand}|${i.shop}|${i.unit}|${i.category}`} aria-label={describeRise(i)}>
                <td>
                  {riseName(i)}
                  <div className="subtitle">per {i.unit}</div>
                </td>
                <td>{i.shop}</td>
                <td className="right">{money(i.latest_price)}</td>
                <td className="right">
                  {money(i.usual_price)}
                  <div className="subtitle">{i.earlier_purchases} earlier</div>
                </td>
                <td className={`right ${isBigRise(i) ? 'up price-rise-big' : 'up'}`}>
                  +{i.rise_pct}%
                  <div className="subtitle">+{money(i.rise_per_unit)}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.total_found > data.items.length && (
        <p className="subtitle">Showing the {data.items.length} biggest of {data.total_found}.</p>
      )}
      {note && <p className="subtitle">{note}</p>}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </section>
  )
}

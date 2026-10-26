import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchCheapestShops } from '../api/client.js'
import { LOOKBACKS, describeSaving, itemName, summaryText, timesText } from '../cheapestShops.js'

// "Where is it cheaper?": items you buy at more than one shop, where a shop you use less has a lower
// price than your usual one. The same product is compared (item, unit, category and brand).
export default function CheapestShopsPanel({ refreshKey }) {
  const [months, setMonths] = useState(12)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)

  useEffect(() => {
    const request = ++latest.current
    fetchCheapestShops({ months })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [months, refreshKey])

  const heading = (
    <div className="period-header">
      <h2>🏷️ Cheapest shop per item</h2>
      <select aria-label="Look back" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
        {LOOKBACKS.map((l) => (
          <option key={l.months} value={l.months}>
            {l.label}
          </option>
        ))}
      </select>
    </div>
  )

  if (error && !data) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Couldn’t load the shop comparison: {error}</p>
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
              <th>Cheapest</th>
              <th>Where you usually buy it</th>
              <th className="right">You’d save</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={`${i.item}|${i.brand}|${i.unit}|${i.category}`} aria-label={describeSaving(i)}>
                <td>
                  {itemName(i)}
                  <div className="subtitle">per {i.unit}</div>
                </td>
                <td>
                  <strong>{i.cheapest.shop}</strong>
                  <div className="subtitle">
                    {money(i.cheapest.avg_price)}, bought {timesText(i.cheapest.times_bought)}
                  </div>
                </td>
                <td>
                  {i.usual.shop}
                  <div className="subtitle">
                    {money(i.usual.avg_price)}, bought {timesText(i.usual.times_bought)}
                  </div>
                </td>
                <td className="right down">
                  {money(i.saving_per_unit)}
                  <div className="subtitle">{i.saving_pct}% less</div>
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

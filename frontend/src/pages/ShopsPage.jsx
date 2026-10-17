import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchShopScorecard } from '../api/client.js'
import { PERIODS, DEFAULT_MONTHS, priceLevel, describeOpportunity, cheapestOn } from '../shopScorecard.js'

const TONE_CLASS = { good: 'down', bad: 'up' } // a cheaper shop is good news, like spending going down

export default function ShopsPage({ onError }) {
  const [months, setMonths] = useState(DEFAULT_MONTHS)
  const [data, setData] = useState(null)
  const latest = useRef(0)

  // Only the newest request may update the page, so a slow answer for an earlier period
  // can't replace the one that was just asked for.
  useEffect(() => {
    const request = ++latest.current
    fetchShopScorecard({ months })
      .then((result) => {
        if (request === latest.current) setData(result)
      })
      .catch((err) => {
        if (request === latest.current) onError(err.message)
      })
  }, [months])

  return (
    <>
      <h1>🏪 Shops</h1>
      <p className="subtitle">
        Where your money goes, how often you shop there, and which shops are cheaper for the things you buy at more
        than one. ICA, ICA Maxi and Ica Nara are separate shops unless you merge them on the Prices page.
      </p>

      <label style={{ display: 'block', margin: '0.75rem 0' }}>
        Period{' '}
        <select aria-label="Period" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {PERIODS.map((p) => (
            <option key={p.months} value={p.months}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      {!data ? (
        <p>Loading…</p>
      ) : !data.available ? (
        <p className="subtitle">No spending with a shop recorded in this period.</p>
      ) : (
        <>
          <section className="panel">
            <table className="table">
              <thead>
                <tr>
                  <th>Shop</th>
                  <th className="right">Spent</th>
                  <th className="right">Share</th>
                  <th className="right">Visits</th>
                  <th className="right">Per visit</th>
                  <th className="right">Visits / month</th>
                  <th className="right">Prices vs other shops</th>
                  <th className="right">Cheapest on</th>
                  <th className="right">Could save</th>
                </tr>
              </thead>
              <tbody>
                {data.shops.map((s) => {
                  const level = priceLevel(s, data.min_items_for_index)
                  return (
                    <tr key={s.shop}>
                      <td>{s.shop}</td>
                      <td className="right">{money(s.spend)}</td>
                      <td className="right">{s.share_pct}%</td>
                      <td className="right">{s.visits}</td>
                      <td className="right">{money(s.avg_visit)}</td>
                      <td className="right">{s.visits_per_month}</td>
                      <td className={`right ${TONE_CLASS[level.tone] || ''}`} title={level.hint}>
                        {level.text}
                      </td>
                      <td className="right">{cheapestOn(s)}</td>
                      <td className="right">{Number(s.potential_saving) > 0 ? money(s.potential_saving) : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {data.unknown.purchases > 0 && (
              <p className="subtitle">
                {money(data.unknown.spend)} across {data.unknown.purchases}{' '}
                {data.unknown.purchases === 1 ? 'purchase has' : 'purchases have'} no shop recorded and{' '}
                {data.unknown.purchases === 1 ? 'is' : 'are'} not included above.
              </p>
            )}
            {data.unconverted_count > 0 && (
              <p className="subtitle">
                {data.unconverted_count} {data.unconverted_count === 1 ? 'expense' : 'expenses'} in a currency without an exchange
                rate {data.unconverted_count === 1 ? 'is' : 'are'} left out.
              </p>
            )}
          </section>

          {data.opportunities.length > 0 && (
            <section className="panel">
              <h2>💡 Where you could save</h2>
              <ul data-testid="opportunities">
                {data.opportunities.map((o, i) => (
                  <li key={i}>{describeOpportunity(o)}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="subtitle">
            <strong>Prices vs other shops</strong> compares each shop with the average shop for the items you buy at two or more
            shops: same item, brand and category, with grams and kilos compared per unit. Items you spend more on count for
            more. It needs at least {data.min_items_for_index} such items, covers only those items (not the shop&rsquo;s whole range),
            and ignores distance and quality. <strong>Could save</strong> is what the same quantities would have cost at the cheapest
            shop for each item.
          </p>
        </>
      )}
    </>
  )
}

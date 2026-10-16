import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchPriceDetail } from '../api/client.js'

const TREND_ICON = { Increasing: '📈', Decreasing: '📉', Stable: '➡️' }
const NO_BRAND = 'No brand'

// One item's price comparison, narrowed to what the user picks: a brand, and which shops to
// include. Everything starts included, and the numbers below always describe exactly the
// current selection.
export default function PriceDetail({ trend, onError }) {
  const [data, setData] = useState(null)
  const [brand, setBrand] = useState(null) // null = every brand, '' = no brand recorded
  const [shops, setShops] = useState(null) // null = every shop, otherwise the ones included
  const latest = useRef(0)

  // (Re)load whenever the selection changes. Only the newest request may update the view,
  // so a slow earlier answer can't overwrite a newer selection.
  useEffect(() => {
    const request = ++latest.current
    fetchPriceDetail({ item: trend.item, unit: trend.unit, category: trend.category, brand, shops })
      .then((result) => {
        if (request === latest.current) setData(result)
      })
      .catch((err) => {
        if (request === latest.current) onError(err.message)
      })
  }, [trend.item, trend.unit, trend.category, brand, shops])

  if (!data) return <p>Loading…</p>

  const brandOptions = data.options.brands
  const shopOptions = data.options.shops
  const allShops = shopOptions.map((s) => s.name)
  const included = shops === null ? allShops : shops

  function chooseBrand(value) {
    setBrand(value === '__all__' ? null : value)
  }

  function toggleShop(name) {
    const next = included.includes(name) ? included.filter((s) => s !== name) : allShops.filter((s) => s === name || included.includes(s))
    if (next.length === 0) return // at least one shop stays in the comparison
    setShops(next.length === allShops.length ? null : next)
  }

  const summary = data.summary

  return (
    <div className="price-detail">
      {(brandOptions.length > 1 || shopOptions.length > 1) && (
        <div className="panel" style={{ marginBottom: '0.75rem' }}>
          <p className="subtitle" style={{ margin: '0 0 0.5rem' }}>
            Choose what to compare. Everything is included until you change it.
          </p>
          {brandOptions.length > 1 && (
            <label style={{ display: 'block', margin: '0.3rem 0' }}>
              Brand{' '}
              <select
                aria-label="Brand"
                value={brand === null ? '__all__' : brand}
                onChange={(e) => chooseBrand(e.target.value)}
              >
                <option value="__all__">All brands</option>
                {brandOptions.map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.name || NO_BRAND} ({b.count})
                  </option>
                ))}
              </select>
            </label>
          )}
          {shopOptions.length > 1 && (
            <fieldset style={{ border: 'none', padding: 0, margin: '0.5rem 0 0' }}>
              <legend>Shops to include</legend>
              {shopOptions.map((s) => (
                <label key={s.name} style={{ display: 'inline-block', marginRight: '1rem' }}>
                  <input
                    type="checkbox"
                    checked={included.includes(s.name)}
                    disabled={included.length === 1 && included.includes(s.name)}
                    onChange={() => toggleShop(s.name)}
                  />{' '}
                  {s.name} ({s.count})
                </label>
              ))}
              {shops !== null && (
                <button type="button" onClick={() => setShops(null)}>
                  Include all shops
                </button>
              )}
            </fieldset>
          )}
        </div>
      )}

      {!summary ? (
        <p className="subtitle">No purchases match this selection.</p>
      ) : (
        <>
          <p data-testid="selection-summary">
            <strong>{summary.purchases}</strong> {summary.purchases === 1 ? 'purchase' : 'purchases'} · average{' '}
            <strong>{money(summary.avg_price)}</strong> per {trend.unit} · lowest {money(summary.min_price)} · highest{' '}
            {money(summary.max_price)}
            {summary.purchases > 1 && (
              <>
                {' '}
                · {TREND_ICON[summary.trend]} {summary.trend} ({summary.change_pct > 0 ? '+' : ''}
                {summary.change_pct}% since the first purchase)
              </>
            )}
          </p>
          {data.shops.length > 0 && (
            <>
              <h3>By shop</h3>
              <table className="table">
                <thead>
                  <tr>
                    <th>Shop</th>
                    <th className="right">Avg</th>
                    <th className="right">Min</th>
                    <th className="right">Max</th>
                    <th className="right">Times bought</th>
                  </tr>
                </thead>
                <tbody>
                  {data.shops.map((s) => (
                    <tr key={s.shop}>
                      <td>{s.shop}</td>
                      <td className="right">{money(s.avg_price)}</td>
                      <td className="right">{money(s.min_price)}</td>
                      <td className="right">{money(s.max_price)}</td>
                      <td className="right">{s.times_bought}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <h3>Timeline</h3>
          <ul className="price-timeline">
            {data.history.map((h, i) => (
              <li key={i}>
                {h.date} — {money(h.price)} {h.shop ? `at ${h.shop}` : ''}
                {h.brand ? ` (${h.brand})` : ''}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

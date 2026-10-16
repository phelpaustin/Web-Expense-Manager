import { useEffect, useState, Fragment } from 'react'
import { money } from '../format.js'
import { fetchPriceTrends } from '../api/client.js'
import PriceDetail from '../components/PriceDetail.jsx'
import TidyNames from '../components/TidyNames.jsx'

const TREND_ICON = { Increasing: '📈', Decreasing: '📉', Stable: '➡️' }

export default function PriceTrackerPage({ onError }) {
  const [trends, setTrends] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  function loadTrends() {
    return fetchPriceTrends()
      .then(setTrends)
      .catch((err) => onError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadTrends()
  }, [])

  // A merge or undo regroups the items, so any open detail row may no longer exist.
  function handleNamesChanged() {
    setSelected(null)
    return loadTrends()
  }

  function selectItem(t) {
    const key = `${t.item}::${t.unit}::${t.category}`
    setSelected(selected === key ? null : key)
  }

  // Case does not matter: "milk" finds "Milk" and "Arla MILK".
  const needle = query.trim().toLowerCase()
  const visible = needle
    ? trends.filter((t) => t.item.toLowerCase().includes(needle) || t.category.toLowerCase().includes(needle))
    : trends

  return (
    <>
      <h1 className="page-title">📈 Price tracker</h1>
      <p className="subtitle">
        See how prices for items you've bought more than once have changed over time, and compare shops. Amounts are
        converted to your base currency. Prices are compared across purchases of the same item and category, in units
        of the same kind: kg and g are converted to a price per kg, litres and ml to a price per litre. A toothpaste
        bought as "1 Count" is still tracked separately from one logged in "kg" or "litre", since those are unrelated
        numbers. Names that differ only by case or spacing count as the same item; different names ("Milk" and "Arla
        Milk") stay separate. Open an item to compare it by brand and to choose which shops to include.
      </p>

      <TidyNames onChanged={handleNamesChanged} onError={onError} />

      {loading ? (
        <p>Loading…</p>
      ) : trends.length === 0 ? (
        <p className="subtitle">Not enough repeat purchases yet — buy the same item (in the same unit) twice to see a price trend.</p>
      ) : (
        <>
          <input
            type="search"
            placeholder="Search items or categories"
            aria-label="Search items"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ marginBottom: '0.75rem' }}
          />
          {visible.length === 0 && <p className="subtitle">No items match “{query.trim()}”.</p>}
          <table className="table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Unit</th>
                <th className="right">First price</th>
                <th className="right">Last price</th>
                <th className="right">Change</th>
                <th>Trend</th>
                <th className="right">Purchases</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => {
                const key = `${t.item}::${t.unit}::${t.category}`
                return (
                  <Fragment key={key}>
                    <tr className="clickable-row" onClick={() => selectItem(t)}>
                      <td>{t.item}</td>
                      <td>{t.category}</td>
                      <td>{t.unit}</td>
                      <td className="right">{money(t.first_price)}</td>
                      <td className="right">{money(t.last_price)}</td>
                      <td className="right" style={{ color: t.change > 0 ? 'var(--danger)' : t.change < 0 ? 'var(--ok)' : undefined }}>
                        {t.change > 0 ? '+' : ''}
                        {money(t.change)} ({t.change_pct > 0 ? '+' : ''}
                        {t.change_pct}%)
                      </td>
                      <td>
                        {TREND_ICON[t.trend]} {t.trend}
                      </td>
                      <td className="right">{t.purchases}</td>
                    </tr>
                    {selected === key && (
                      <tr>
                        <td colSpan={8}>
                          <PriceDetail trend={t} onError={onError} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}

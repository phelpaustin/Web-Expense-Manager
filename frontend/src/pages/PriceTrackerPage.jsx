import { useEffect, useState, Fragment } from 'react'
import { money } from '../format.js'
import { fetchPriceTrends, fetchPriceShopComparison, fetchPriceHistory } from '../api/client.js'

const TREND_ICON = { Increasing: '📈', Decreasing: '📉', Stable: '➡️' }

export default function PriceTrackerPage({ onError }) {
  const [trends, setTrends] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    fetchPriceTrends()
      .then(setTrends)
      .catch((err) => onError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function selectItem(item) {
    if (selected === item) {
      setSelected(null)
      setDetail(null)
      return
    }
    setSelected(item)
    try {
      const [shops, history] = await Promise.all([fetchPriceShopComparison(item), fetchPriceHistory(item)])
      setDetail({ shops, history })
    } catch (err) {
      onError(err.message)
    }
  }

  return (
    <>
      <h1 className="page-title">📈 Price tracker</h1>
      <p className="subtitle">
        See how prices for items you've bought more than once have changed over time, and compare shops.
      </p>

      {loading ? (
        <p>Loading…</p>
      ) : trends.length === 0 ? (
        <p className="subtitle">Not enough repeat purchases yet — buy the same item twice to see a price trend.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Category</th>
              <th className="right">First price</th>
              <th className="right">Last price</th>
              <th className="right">Change</th>
              <th>Trend</th>
              <th className="right">Purchases</th>
            </tr>
          </thead>
          <tbody>
            {trends.map((t) => (
              <Fragment key={t.item}>
                <tr className="clickable-row" onClick={() => selectItem(t.item)}>
                  <td>{t.item}</td>
                  <td>{t.category}</td>
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
                {selected === t.item && detail && (
                  <tr>
                    <td colSpan={7}>
                      <div className="price-detail">
                        {detail.shops.length > 0 && (
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
                                {detail.shops.map((s) => (
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
                          {detail.history.map((h, i) => (
                            <li key={i}>
                              {h.date} — {money(h.price)} {h.shop ? `at ${h.shop}` : ''}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

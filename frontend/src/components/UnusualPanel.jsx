import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { money } from '../format.js'
import { fetchUnusual } from '../api/client.js'
import { allClearText, describeDuplicate, describeUnusual, entryName, hasFindings, ratioText } from '../unusual.js'

// "Worth a look": recent expenses far above what you usually spend in that category, and entries that
// look like they were entered twice. Only suggestions: nothing is changed or deleted from here.
export default function UnusualPanel({ scope, spaceIds, refreshKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)

  useEffect(() => {
    const request = ++latest.current
    fetchUnusual({ scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
    // spaceIds is a fresh array each render; the scope key in the parent remounts on a real change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, refreshKey])

  const heading = <h2>🔎 Worth a look</h2>

  if (error && !data) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Couldn’t load this: {error}</p>
      </section>
    )
  }
  if (!data || !data.unusual || !Array.isArray(data.unusual.items) || !data.duplicates || !Array.isArray(data.duplicates.items)) {
    return (
      <section className="panel">
        {heading}
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  const { unusual, duplicates } = data

  return (
    <section className="panel">
      {heading}
      {!hasFindings(data) && <p className="subtitle">{allClearText(data)}</p>}

      {unusual.items.length > 0 && (
        <>
          <h3>Bigger than usual</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Expense</th>
                <th>Date</th>
                <th className="right">Amount</th>
                <th className="right">Usually</th>
              </tr>
            </thead>
            <tbody>
              {unusual.items.map((i) => (
                <tr key={i.id} aria-label={describeUnusual(i)}>
                  <td>
                    {entryName(i)}
                    <div className="subtitle">{i.category}</div>
                  </td>
                  <td>{i.date}</td>
                  <td className="right up">
                    {money(i.amount)}
                    <div className="subtitle">{ratioText(i.ratio)} usual</div>
                  </td>
                  <td className="right">{money(i.usual)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {unusual.total_found > unusual.items.length && (
            <p className="subtitle">Showing the {unusual.items.length} biggest of {unusual.total_found}.</p>
          )}
        </>
      )}

      {duplicates.items.length > 0 && (
        <>
          <h3>Entered twice?</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Expense</th>
                <th>Date</th>
                <th className="right">Amount</th>
                <th className="right">Entries</th>
              </tr>
            </thead>
            <tbody>
              {duplicates.items.map((d) => (
                <tr key={`${d.date}|${d.amount}|${d.description}|${d.shop}|${d.category}`} aria-label={describeDuplicate(d)}>
                  <td>
                    {entryName(d)}
                    <div className="subtitle">{d.category}</div>
                  </td>
                  <td>{d.date}</td>
                  <td className="right">{money(d.amount)}</td>
                  <td className="right">{d.count}×</td>
                </tr>
              ))}
            </tbody>
          </table>
          {duplicates.total_found > duplicates.items.length && (
            <p className="subtitle">Showing the {duplicates.items.length} newest of {duplicates.total_found}.</p>
          )}
        </>
      )}

      {hasFindings(data) && (
        <p className="subtitle">
          These are only suggestions. <Link to="/spending?view=items">Review them under Spending</Link>.
        </p>
      )}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </section>
  )
}

import { useEffect, useRef, useState } from 'react'
import { money } from '../format.js'
import { fetchMovers } from '../api/client.js'
import { monthLabel, signedMoney } from '../categoryChange.js'
import { partialNote, pctText } from '../periodCompare.js'

const GROUPS = [
  { key: 'rose', title: 'Rose most', empty: 'Nothing rose.' },
  { key: 'fell', title: 'Fell most', empty: 'Nothing fell.' },
  { key: 'new', title: 'New this month', empty: 'Nothing new.' },
]

function Row({ row, kind }) {
  const up = Number(row.change) > 0
  return (
    <li className="mover-row">
      <span className="mover-name">{row.name}</span>
      {kind === 'new' ? (
        <span className="mover-change">{money(row.now)}</span>
      ) : (
        <span className={`mover-change ${up ? 'up' : 'down'}`}>
          {row.status === 'stopped' ? `none this month (${signedMoney(row.change)})` : signedMoney(row.change)}
          {row.status !== 'stopped' && pctText(row) && ` (${pctText(row)})`}
        </span>
      )}
    </li>
  )
}

function Column({ title, lists }) {
  return (
    <div className="movers-col">
      <h3>{title}</h3>
      {GROUPS.map((g) => (
        <div key={g.key} className="movers-group">
          <span className="card-label">{g.title}</span>
          {lists[g.key].length === 0 ? (
            <p className="subtitle">{g.empty}</p>
          ) : (
            <ul className="movers-list">
              {lists[g.key].map((r) => (
                <Row key={r.name} row={r} kind={g.key} />
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  )
}

// "What moved?": the categories and shops that rose most, fell most or are new, against the month
// before. The month is the one chosen in "Compared with" above it.
export default function MoversPanel({ month = null, scope, spaceIds, refreshKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const latest = useRef(0)
  const idsKey = (spaceIds || []).join(',')

  useEffect(() => {
    const request = ++latest.current
    fetchMovers({ month, scope, spaceIds })
      .then((result) => {
        if (request !== latest.current) return
        setData(result)
        setError(null)
      })
      .catch((err) => {
        if (request === latest.current) setError(err.message)
      })
  }, [month, scope, idsKey, refreshKey])

  if (error && !data) {
    return (
      <section className="panel">
        <h2>🚀 Biggest movers</h2>
        <p className="subtitle">Couldn’t load the movers: {error}</p>
      </section>
    )
  }
  if (!data || !data.categories || !data.shops) {
    return (
      <section className="panel">
        <h2>🚀 Biggest movers</h2>
        <p className="subtitle">Loading…</p>
      </section>
    )
  }

  return (
    <section className="panel">
      <h2>🚀 Biggest movers</h2>
      <p className="subtitle">
        {monthLabel(data.month)}
        {data.partial ? ' so far' : ''} against {monthLabel(data.compare_month)}.
      </p>

      {!data.available ? (
        <p className="subtitle">Not enough history yet: there is nothing before {monthLabel(data.month)} to compare with.</p>
      ) : (
        <div className="movers-grid">
          <Column title="Categories" lists={data.categories} />
          <Column title="Shops" lists={data.shops} />
        </div>
      )}

      {data.partial && <p className="subtitle">{partialNote(data)}</p>}
      {error && <p className="subtitle">Couldn’t refresh: {error}</p>}
    </section>
  )
}

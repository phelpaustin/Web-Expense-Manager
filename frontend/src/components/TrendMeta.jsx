const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "2026-09" -> "Sep"
export function monthName(key) {
  const n = Number(String(key || '').slice(5, 7))
  return MONTHS[n - 1] || key
}

// Month-over-month change under the spending chart. It is based on finished months only; the
// in-progress month is called out instead of being counted. (The forecast has its own panel.)
export default function TrendMeta({ trends }) {
  const { change, current_month: current } = trends
  const pct = change?.pct_change
  const arrow = change?.direction === 'up' ? '▲' : change?.direction === 'down' ? '▼' : '■'
  return (
    <>
      <div className="trend-meta">
        {change && (
          <span>
            {monthName(change.last_month)} vs {monthName(change.previous_month)}:{' '}
            <strong className={change.direction === 'up' ? 'up' : 'down'}>
              {arrow} {pct == null ? 'n/a (no spend before)' : `${Math.abs(pct)}%`}
            </strong>
          </span>
        )}
      </div>
      {current && (
        <small className="muted">
          {monthName(current)} is still in progress, so it is left out of the change.
        </small>
      )}
    </>
  )
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// How a month-over-month change reads: an arrow, the size, and the colour class. A change with no
// earlier spend to compare with has no percentage, and a flat month is neither up nor down.
export function describeChange(change) {
  const pct = change?.pct_change
  const direction = change?.direction
  return {
    arrow: direction === 'up' ? '▲' : direction === 'down' ? '▼' : '■',
    text: pct == null ? 'n/a (no spend before)' : `${Math.abs(pct)}%`,
    className: direction === 'up' ? 'up' : direction === 'down' ? 'down' : '',
  }
}

// "2026-09" -> "Sep"
function monthName(key) {
  const n = Number(String(key || '').slice(5, 7))
  return MONTHS[n - 1] || key
}

// Month-over-month change under the spending chart. It is based on finished months only; the
// in-progress month is called out instead of being counted. (The forecast has its own panel.)
export default function TrendMeta({ trends }) {
  const { change, current_month: current } = trends
  const shown = describeChange(change)
  return (
    <>
      <div className="trend-meta">
        {change && (
          <span>
            {monthName(change.last_month)} vs {monthName(change.previous_month)}:{' '}
            <strong className={shown.className}>
              {shown.arrow} {shown.text}
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

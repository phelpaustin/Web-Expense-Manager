import { DATE_PRESETS, CUSTOM_RANGE, PICK_MONTH, PICK_YEAR, defaultValueFor } from '../datePeriod.js'

// Period dropdown plus whatever it needs: a month picker, a year, or a from/to range.
export default function DatePeriodFilter({ filter, onChange }) {
  const { period, value, from, to } = filter
  return (
    <>
      <select
        aria-label="Date"
        title="Show expenses from…"
        value={period}
        onChange={(e) => {
          const next = e.target.value
          onChange({ period: next, value: defaultValueFor(next), from: '', to: '' })
        }}
      >
        {DATE_PRESETS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
        <option value={PICK_MONTH}>A particular month…</option>
        <option value={PICK_YEAR}>A particular year…</option>
        <option value={CUSTOM_RANGE}>Custom range…</option>
      </select>
      {period === PICK_MONTH && (
        <input type="month" aria-label="Month" value={value} onChange={(e) => onChange({ ...filter, value: e.target.value })} />
      )}
      {period === PICK_YEAR && (
        <input
          type="number"
          aria-label="Year"
          min="1990"
          max="2100"
          step="1"
          placeholder="Year"
          value={value}
          onChange={(e) => onChange({ ...filter, value: e.target.value })}
        />
      )}
      {period === CUSTOM_RANGE && (
        <>
          <input type="date" aria-label="From date" title="From date" value={from} onChange={(e) => onChange({ ...filter, from: e.target.value })} />
          <input type="date" aria-label="To date" title="To date" value={to} onChange={(e) => onChange({ ...filter, to: e.target.value })} />
        </>
      )}
    </>
  )
}

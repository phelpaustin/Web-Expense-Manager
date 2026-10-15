// Unit dropdown for an expense's quantity (Count, Kg, Litre, ...).
// Shows the user's own units (Settings → Units) plus common ones, and always keeps the
// current value selectable, e.g. a custom unit that came from an import.
export const COMMON_UNITS = ['Count', 'Pack', 'Kg', 'Gram', 'Litre', 'Millilitre', 'Meter']

export function unitChoices(userUnits = [], current = '') {
  const seen = new Set()
  const out = []
  for (const u of [...userUnits, ...COMMON_UNITS, current]) {
    const name = String(u || '').trim()
    const key = name.toLowerCase()
    if (name && !seen.has(key)) {
      seen.add(key)
      out.push(name)
    }
  }
  return out
}

export default function UnitSelect({ value, onChange, units, className = 'unit-input', label = 'Unit' }) {
  const current = value || 'Count'
  return (
    <select
      className={className}
      value={current}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      title={label}
    >
      {unitChoices(units, current).map((u) => (
        <option key={u} value={u}>
          {u}
        </option>
      ))}
    </select>
  )
}

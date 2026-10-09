// Currency dropdown fed by the currencies the backend can convert.
// With `allowDefault` the first option means "let the server pick": the
// space's currency, else the user's base currency (shown in the label).
export default function CurrencySelect({
  value,
  onChange,
  currencies = [],
  defaultCurrency,
  defaultLabel = 'Default',
  allowDefault = true,
  disabled = false,
  title = 'Currency',
  className = 'unit-input',
}) {
  // Keep an unsupported legacy value selectable so editing it is possible.
  const list = value && !currencies.includes(value) ? [value, ...currencies] : currencies
  return (
    <select className={className} value={value || ''} disabled={disabled} title={title} onChange={(e) => onChange(e.target.value)}>
      {allowDefault && <option value="">{defaultLabel}{defaultCurrency ? ` (${defaultCurrency})` : ''}</option>}
      {list.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  )
}

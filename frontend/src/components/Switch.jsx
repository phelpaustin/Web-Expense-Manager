// An on/off switch (a styled checkbox with role="switch"), with an optional explanation line.
export default function Switch({ checked, onChange, label, description, title }) {
  return (
    <label className="switch-row" title={title}>
      <span className="switch">
        <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      </span>
      <span className="switch-text">
        <strong>{label}</strong>
        {description && <small>{description}</small>}
      </span>
    </label>
  )
}

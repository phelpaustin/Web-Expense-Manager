import { useState } from 'react'

const CHOOSE_SPACES = '__choose__'

// The page title plus the "which expenses?" picker shared by the Dashboard and Insights: all expenses,
// personal only, one Expense Space, or a combination. The choice itself lives in app state, so it
// follows you from one page to the other.
export default function ScopePicker({
  title,
  groups,
  trips,
  dashboardScope,
  onSetDashboardScope,
  dashboardSpaceIds,
  onSetDashboardSpaceIds,
}) {
  const [choosingSpaces, setChoosingSpaces] = useState(false)
  const [pendingSelection, setPendingSelection] = useState(dashboardSpaceIds || [])
  const multiActive = dashboardSpaceIds && dashboardSpaceIds.length > 0
  const allSpaces = (groups || []).concat(trips || [])

  function spaceLabel(id) {
    if (id === 'personal') return 'Personal expenses'
    return allSpaces.find((g) => String(g.id) === String(id))?.name || id
  }

  function handleSelectChange(value) {
    if (value === CHOOSE_SPACES) {
      setPendingSelection(dashboardSpaceIds && dashboardSpaceIds.length ? dashboardSpaceIds : ['personal'])
      setChoosingSpaces(true)
      return
    }
    setChoosingSpaces(false)
    onSetDashboardScope(value)
  }

  function toggleSpace(id) {
    setPendingSelection((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]))
  }

  function applySelection() {
    onSetDashboardSpaceIds(pendingSelection)
    setChoosingSpaces(false)
  }

  return (
    <>
      <div className="dashboard-header">
        <h1 className="page-title">{title}</h1>
        {allSpaces.length > 0 && (
          <div className="scope-picker">
            <select
              className="scope-select"
              value={multiActive ? CHOOSE_SPACES : dashboardScope}
              onChange={(e) => handleSelectChange(e.target.value)}
              title="Show data for personal expenses only, one Expense Space, or a combined view"
            >
              <option value="all">All expenses</option>
              <option value="personal">Personal expenses</option>
              {allSpaces.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
              <option value={CHOOSE_SPACES}>Choose spaces…</option>
            </select>
            {multiActive && !choosingSpaces && (
              <span className="subtitle">Selected spaces: {dashboardSpaceIds.map(spaceLabel).join(', ')}</span>
            )}
          </div>
        )}
      </div>

      {choosingSpaces && (
        <section className="panel">
          <h2>🗂️ Choose Expense Spaces</h2>
          <p className="subtitle">Combine two or more spaces into one view.</p>
          <ul className="space-checklist">
            <li>
              <label>
                <input
                  type="checkbox"
                  checked={pendingSelection.includes('personal')}
                  onChange={() => toggleSpace('personal')}
                />
                Personal expenses
              </label>
            </li>
            {allSpaces.map((g) => (
              <li key={g.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={pendingSelection.includes(String(g.id))}
                    onChange={() => toggleSpace(String(g.id))}
                  />
                  {g.name}
                </label>
              </li>
            ))}
          </ul>
          <div className="auto-cat-row">
            <button type="button" onClick={applySelection} disabled={pendingSelection.length === 0}>
              Apply
            </button>
            <button type="button" className="ghost-btn" onClick={() => setChoosingSpaces(false)}>
              Cancel
            </button>
          </div>
        </section>
      )}
    </>
  )
}

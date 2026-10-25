import DatePeriodFilter from '../DatePeriodFilter.jsx'
import { SPACE_TYPE_ICONS } from './shared.jsx'

export default function ExpenseFilters({
  options,
  search,
  filterCategory,
  filterShop,
  filterGroup,
  dateFilter,
  setDateFilter,
  selectMode,
  groupByBill,
  setGroupByBill,
  filterTotalOnly,
  allSpaces,
  hasActiveFilters,
  clearFilters,
  resetToFirstPage,
  setSearch,
  setFilterCategory,
  setFilterShop,
  setFilterGroup,
  setFilterTotalOnly,
  toggleSelectMode,
}) {
  return (
    <section className="panel">
      <h2>🔍 Search &amp; filter</h2>
      <div className="add-form">
        <input
          type="text"
          placeholder="Search item, shop, brand…"
          value={search}
          onChange={(e) => resetToFirstPage(setSearch)(e.target.value)}
        />
        <select value={filterCategory} onChange={(e) => resetToFirstPage(setFilterCategory)(e.target.value)}>
          <option value="">All categories</option>
          {options.categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select value={filterShop} onChange={(e) => resetToFirstPage(setFilterShop)(e.target.value)}>
          <option value="">All shops</option>
          {(options.shops || []).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {allSpaces.length > 0 && (
          <select value={filterGroup} onChange={(e) => resetToFirstPage(setFilterGroup)(e.target.value)}>
            <option value="">All expenses</option>
            <option value="personal">Personal expenses</option>
            {allSpaces.map((g) => (
              <option key={g.id} value={g.id}>
                {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
              </option>
            ))}
          </select>
        )}
        <DatePeriodFilter filter={dateFilter} onChange={resetToFirstPage(setDateFilter)} />
        <label className="toggle-row inline-toggle" title="Show only expenses that are a bill's total with no items yet">
          <input
            type="checkbox"
            checked={filterTotalOnly}
            onChange={(e) => resetToFirstPage(setFilterTotalOnly)(e.target.checked)}
          />
          <span>Total-only bills</span>
        </label>
        {hasActiveFilters && (
          <button type="button" className="ghost-btn" onClick={clearFilters}>
            Clear filters
          </button>
        )}
        <button type="button" className="ghost-btn" onClick={toggleSelectMode} aria-pressed={selectMode}>
          {selectMode ? '✕ Stop editing together' : '☑ Edit together'}
        </button>
        <button type="button" className="ghost-btn" onClick={() => setGroupByBill((v) => !v)}>
          {groupByBill ? '📄 Flat view' : '🧾 Bill view'}
        </button>
      </div>
    </section>
  )
}

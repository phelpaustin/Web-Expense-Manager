import { SPACE_TYPE_ICONS, KEEP } from './shared.jsx'

export default function BulkEditPanel({
  pageExpenses,
  allMatching,
  setAllMatching,
  bulk,
  setBulk,
  bulkBusy,
  bulkNotice,
  total,
  allSpaces,
  selectedCount,
  pageAllSelected,
  clearSelection,
  hasBulkChanges,
  describeBulkChanges,
  applyBulk,
  copyTarget,
  setCopyTarget,
  applyCopy,
}) {
  return (
    <section className="panel bulk-bar" data-testid="bulk-bar">
      <h2>✏️ Edit together</h2>
      <p className="subtitle">
        Tick the expenses (or a whole bill) to change, then fill in only what should change. Everything else stays as it is.
      </p>
      <p data-testid="bulk-count" className="bulk-count">
        {selectedCount === 0
          ? 'Nothing selected yet.'
          : allMatching
            ? `All ${total} matching expenses are selected.`
            : `${selectedCount} selected.`}{' '}
        {!allMatching && pageAllSelected && total > pageExpenses.length && (
          <button type="button" className="mini-btn" onClick={() => setAllMatching(true)}>
            Select all {total} matching
          </button>
        )}{' '}
        {selectedCount > 0 && (
          <button type="button" className="mini-btn" onClick={clearSelection}>
            Clear selection
          </button>
        )}
      </p>
      <div className="edit-grid">
        <label className="edit-field">
          <span>Category</span>
          <input
            type="text"
            list="cat-options"
            placeholder="Leave unchanged"
            value={bulk.category}
            onChange={(e) => setBulk({ ...bulk, category: e.target.value })}
          />
        </label>
        <label className="edit-field">
          <span>Subcategory</span>
          <input
            type="text"
            list="subcat-bulk-options"
            placeholder="Leave unchanged"
            value={bulk.subcategory}
            onChange={(e) => setBulk({ ...bulk, subcategory: e.target.value })}
          />
        </label>
        <label className="edit-field">
          <span>Shop</span>
          <input
            type="text"
            list="shop-options"
            placeholder="Leave unchanged"
            value={bulk.shop}
            onChange={(e) => setBulk({ ...bulk, shop: e.target.value })}
          />
        </label>
        <label className="edit-field">
          <span>Item name</span>
          <input
            type="text"
            placeholder="Leave unchanged"
            value={bulk.description}
            onChange={(e) => setBulk({ ...bulk, description: e.target.value })}
          />
        </label>
        {allSpaces.length > 0 && (
          <label className="edit-field">
            <span>Space</span>
            <select value={bulk.group_id} onChange={(e) => setBulk({ ...bulk, group_id: e.target.value })}>
              <option value={KEEP}>Leave unchanged</option>
              <option value="">Personal expenses</option>
              {allSpaces
                .filter((g) => g.role !== 'viewer')
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
                  </option>
                ))}
            </select>
          </label>
        )}
      </div>
      {hasBulkChanges && selectedCount > 0 && (
        <p className="subtitle" data-testid="bulk-summary">
          Will set {describeBulkChanges()} on {selectedCount} expense{selectedCount === 1 ? '' : 's'}.
        </p>
      )}
      <div className="edit-actions">
        <button
          type="button"
          className="primary-btn"
          disabled={bulkBusy || selectedCount === 0 || !hasBulkChanges}
          onClick={applyBulk}
        >
          {bulkBusy ? 'Saving…' : `Apply to ${selectedCount} expense${selectedCount === 1 ? '' : 's'}`}
        </button>
      </div>
      {allSpaces.some((g) => g.role !== 'viewer') && (
        <div className="bulk-copy">
          <h3>Copy to a space</h3>
          <p className="subtitle">
            Makes a new copy of each selected expense in the space and leaves the original where it is. Both count in your
            spending. To move one instead, use Space above.
          </p>
          <div className="edit-actions">
            <select aria-label="Copy to space" value={copyTarget} onChange={(e) => setCopyTarget(e.target.value)}>
              <option value="">Choose a space…</option>
              {allSpaces
                .filter((g) => g.role !== 'viewer')
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {SPACE_TYPE_ICONS[g.space_type] || '✈️'} {g.name}
                  </option>
                ))}
            </select>
            <button
              type="button"
              className="primary-btn"
              disabled={bulkBusy || selectedCount === 0 || !copyTarget}
              onClick={applyCopy}
            >
              {bulkBusy ? 'Copying…' : `Copy ${selectedCount} expense${selectedCount === 1 ? '' : 's'}`}
            </button>
          </div>
        </div>
      )}
      {bulkNotice && (
        <p role="status" className="subtitle">
          {bulkNotice}
        </p>
      )}
    </section>
  )
}

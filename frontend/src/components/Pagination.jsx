// "Showing 1–25 of 312" with page-size and prev/next controls. Pages are 1-based.
export default function Pagination({ page, pageSize, total, onPage, onPageSize, pageSizes = [25, 50, 100] }) {
  if (!total) return null
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(Math.max(page, 1), totalPages)
  const start = (current - 1) * pageSize
  return (
    <div className="pagination-bar">
      <span className="subtitle">
        Showing {start + 1}–{Math.min(start + pageSize, total)} of {total}
      </span>
      <div className="pagination-controls">
        <select
          aria-label="Rows per page"
          value={pageSize}
          onChange={(e) => onPageSize(Number(e.target.value))}
        >
          {pageSizes.map((n) => (
            <option key={n} value={n}>
              {n} / page
            </option>
          ))}
        </select>
        <button type="button" className="ghost-btn" disabled={current <= 1} onClick={() => onPage(current - 1)}>
          ← Prev
        </button>
        <span className="subtitle">
          Page {current} of {totalPages}
        </span>
        <button type="button" className="ghost-btn" disabled={current >= totalPages} onClick={() => onPage(current + 1)}>
          Next →
        </button>
      </div>
    </div>
  )
}

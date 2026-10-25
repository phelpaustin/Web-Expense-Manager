import { PAGE_SIZES } from './shared.jsx'

export default function ExpensePager({ setPage, pageSize, setPageSize, total, totalPages, currentPage, pageStart }) {
  return (
    <div className="pagination-bar">
      <span className="subtitle">
        Showing {pageStart + 1}–{Math.min(pageStart + pageSize, total)} of {total}
      </span>
      <div className="pagination-controls">
        <select
          value={pageSize}
          onChange={(e) => {
            setPageSize(Number(e.target.value))
            setPage(1)
          }}
        >
          {PAGE_SIZES.map((n) => (
            <option key={n} value={n}>
              {n} / page
            </option>
          ))}
        </select>
        <button type="button" className="ghost-btn" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>
          ← Prev
        </button>
        <span className="subtitle">
          Page {currentPage} of {totalPages}
        </span>
        <button type="button" className="ghost-btn" disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}>
          Next →
        </button>
      </div>
    </div>
  )
}

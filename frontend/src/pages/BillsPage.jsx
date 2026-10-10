import { useEffect, useState } from 'react'
import CurrencySelect from '../components/CurrencySelect.jsx'
import Pagination from '../components/Pagination.jsx'
import { BillStatusChip } from '../components/BillStatus.jsx'
import { money } from '../format.js'

const TABS = [
  { key: 'pending', label: 'To itemise' },
  { key: 'total_only', label: 'Total only' },
  { key: 'itemised', label: 'Itemised' },
  { key: 'all', label: 'All' },
]

const EMPTY_TEXT = {
  pending: 'Nothing is waiting to be itemised.',
  total_only: 'No bills are recorded as a total only.',
  itemised: 'No itemised bills yet.',
  all: 'No bills yet. Upload a receipt, import a bank statement, or add one by hand.',
}

const SORTS = [
  { key: 'date_desc', label: 'Newest first' },
  { key: 'date_asc', label: 'Oldest first' },
  { key: 'amount_desc', label: 'Amount: high to low' },
  { key: 'amount_asc', label: 'Amount: low to high' },
  { key: 'shop', label: 'Shop A–Z' },
]

function FileButton({ className = 'link-btn', title, accept, onFile, children }) {
  return (
    <label className={className} title={title}>
      {children}
      <input
        type="file"
        accept={accept}
        onChange={(e) => {
          const f = e.target.files[0]
          if (f) onFile(f)
          e.target.value = ''
        }}
      />
    </label>
  )
}

function BillRow({ bill, selected, onToggle, actions, recordCategory }) {
  const { status } = bill
  return (
    <tr className={bill.possible_duplicate ? 'row-flagged' : ''}>
      <td className="check-col">
        <input type="checkbox" aria-label={`Select ${bill.shop}`} checked={selected} onChange={onToggle} />
      </td>
      <td className="nowrap">
        {bill.date}
        {bill.possible_duplicate && (
          <span className="duplicate-badge" title="Same date and amount as an existing expense or bill. Review before recording it.">
            ⚠ possible duplicate
          </span>
        )}
      </td>
      <td>
        {bill.shop}
        {bill.note && bill.note !== 'Bulk import' && <span className="bill-note"> · {bill.note}</span>}
      </td>
      <td className="right nowrap">{Number(bill.amount) > 0 ? money(bill.amount, bill.currency) : <em className="muted">no amount</em>}</td>
      <td>
        <BillStatusChip status={status} itemCount={bill.item_count} />
      </td>
      <td className="nowrap">
        {bill.has_receipt ? (
          <>
            <button type="button" className="link-btn" onClick={() => actions.viewReceipt(bill.id)} title="View the attached receipt">
              📎 View
            </button>
            <button type="button" className="link-btn danger" onClick={() => actions.deleteReceipt(bill.id)} title="Remove the receipt">
              ✕
            </button>
          </>
        ) : (
          <FileButton title="Attach a PDF or photo of the receipt" accept="application/pdf,image/*" onFile={(f) => actions.uploadReceipt(bill.id, f)}>
            ＋ Attach
          </FileButton>
        )}
      </td>
      <td className="right nowrap bill-actions">
        {bill.possible_duplicate && (
          <button type="button" className="mini-btn" onClick={() => actions.dismissDuplicate(bill.id)} title="Clear the duplicate warning">
            Not a duplicate
          </button>
        )}
        {status !== 'itemised' && (
          <button type="button" className="mini-btn primary" onClick={() => actions.itemise(bill)} title="Enter the items on this bill">
            Itemise
          </button>
        )}
        {status === 'pending' && (
          <button
            type="button"
            className="mini-btn"
            onClick={() => actions.recordTotal(bill, recordCategory)}
            title="Count the whole amount as spending now; itemise whenever you like"
          >
            Record total
          </button>
        )}
        {status === 'total_only' && (
          <button type="button" className="mini-btn" onClick={() => actions.undo(bill)} title="Remove the recorded total and return this bill to 'To itemise'">
            Undo
          </button>
        )}
        {status !== 'total_only' && (
          <button type="button" className="mini-btn danger" onClick={() => actions.remove(bill)} title="Delete this bill">
            Delete
          </button>
        )}
      </td>
    </tr>
  )
}

// state is the object returned by useBillsHandlers.
export default function BillsPage({ state, options }) {
  const { data, query, setQuery, loading, selected, toggleSelect, selectPage, clearSelection, notice, setNotice, form, setForm, actions } = state
  const [showAdd, setShowAdd] = useState(false)
  const [searchText, setSearchText] = useState(query.q)
  const [recordCategory, setRecordCategory] = useState('Bills')

  // Debounce the search box so it doesn't query on every keystroke.
  useEffect(() => {
    const handle = setTimeout(() => {
      if (searchText.trim() !== query.q) setQuery({ q: searchText.trim() })
    }, 400)
    return () => clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText])

  const categories = [...new Set(['Bills', ...(options.categories || [])])]
  const countAsSpending = options.count_bills_as_spending !== false
  const items = data.items
  const allOnPageSelected = items.length > 0 && items.every((b) => selected.has(b.id))
  const filtered = query.q || query.date_from || query.date_to

  return (
    <>
      <h1 className="page-title">📒 Bills</h1>

      <section className="panel">
        <div className="bills-head">
          <div className="bills-actions">
            <FileButton className="btn-upload" accept="application/pdf,image/*" onFile={actions.uploadBill}>
              📤 Upload receipt
            </FileButton>
            <FileButton className="btn-upload btn-upload-bulk" accept=".xlsx,.csv" onFile={actions.bulkUpload}>
              📊 Import bank statement
            </FileButton>
            <button type="button" className="ghost-btn" onClick={() => setShowAdd((v) => !v)}>
              {showAdd ? '✕ Close' : '➕ Add bill'}
            </button>
          </div>
          <label className="toggle-row" title="When on, a bill's whole amount counts towards your budgets as soon as it is added. You can itemise it any time; the items then replace the total.">
            <input type="checkbox" checked={countAsSpending} onChange={(e) => actions.toggleCount(e.target.checked)} />
            <span>
              Count new bills as spending right away
              <small>{countAsSpending ? 'On: bills go to “Total only” and count towards budgets. Itemise whenever you like.' : 'Off: bills wait in “To itemise” and are not counted until you record or itemise them.'}</small>
            </span>
          </label>
        </div>

        {notice && (
          <div className="notice">
            <p>{notice.text}</p>
            {notice.details?.length > 0 && (
              <ul className="notice-details">
                {notice.details.slice(0, 20).map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
                {notice.details.length > 20 && <li>…and {notice.details.length - 20} more</li>}
              </ul>
            )}
            <button className="icon-btn" onClick={() => setNotice(null)} title="Dismiss">
              ✕
            </button>
          </div>
        )}

        {showAdd && (
          <form className="add-form" onSubmit={actions.add}>
            <input type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            <input type="text" placeholder="Shop" required value={form.shop} onChange={(e) => setForm({ ...form, shop: e.target.value })} />
            <input type="text" placeholder="Note (optional)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            <input
              type="number"
              step="0.01"
              min="0.01"
              placeholder="Amount"
              required
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <CurrencySelect
              value={form.currency}
              onChange={(c) => setForm({ ...form, currency: c })}
              currencies={options.currencies}
              defaultCurrency={options.base_currency}
            />
            <button type="submit">Add</button>
          </form>
        )}

        <div className="tabs bill-tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={query.status === t.key}
              className={`tab${query.status === t.key ? ' active' : ''}`}
              onClick={() => setQuery({ status: t.key })}
            >
              {t.label} <span className="tab-count">{data.counts[t.key] ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="bill-toolbar">
          <input
            type="search"
            placeholder="Search shop or note"
            aria-label="Search bills"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          <input type="date" title="From date" aria-label="From date" value={query.date_from} onChange={(e) => setQuery({ date_from: e.target.value })} />
          <input type="date" title="To date" aria-label="To date" value={query.date_to} onChange={(e) => setQuery({ date_to: e.target.value })} />
          <select aria-label="Sort" value={query.sort} onChange={(e) => setQuery({ sort: e.target.value })}>
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          {filtered && (
            <button
              type="button"
              className="ghost-btn"
              onClick={() => {
                setSearchText('')
                setQuery({ q: '', date_from: '', date_to: '' })
              }}
            >
              Clear filters
            </button>
          )}
        </div>

        {selected.size > 0 && (
          <div className="bulk-bar" role="region" aria-label="Selected bills">
            <strong>{selected.size} selected</strong>
            <span className="bulk-record">
              Record as
              <select aria-label="Category for recorded totals" value={recordCategory} onChange={(e) => setRecordCategory(e.target.value)}>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button type="button" className="mini-btn primary" onClick={() => actions.bulkRecord(recordCategory)}>
                Record total
              </button>
            </span>
            <button type="button" className="mini-btn danger" onClick={actions.bulkDelete}>
              Delete
            </button>
            <button type="button" className="mini-btn" onClick={clearSelection}>
              Clear
            </button>
          </div>
        )}

        {loading && items.length === 0 ? (
          <p className="subtitle">Loading…</p>
        ) : items.length === 0 ? (
          <p className="empty-state">{filtered ? 'No bills match your search.' : EMPTY_TEXT[query.status]}</p>
        ) : (
          <div className="table-scroll">
            <table className="table bills-table">
              <thead>
                <tr>
                  <th className="check-col">
                    <input
                      type="checkbox"
                      aria-label="Select all bills on this page"
                      checked={allOnPageSelected}
                      onChange={() => (allOnPageSelected ? items.forEach((b) => toggleSelect(b.id)) : selectPage())}
                    />
                  </th>
                  <th>Date</th>
                  <th>Shop</th>
                  <th className="right">Amount</th>
                  <th>Status</th>
                  <th>Receipt</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((b) => (
                  <BillRow
                    key={b.id}
                    bill={b}
                    selected={selected.has(b.id)}
                    onToggle={() => toggleSelect(b.id)}
                    actions={actions}
                    recordCategory={recordCategory}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Pagination
          page={data.page}
          pageSize={query.page_size}
          total={data.total}
          onPage={(p) => setQuery({ page: p })}
          onPageSize={(n) => setQuery({ page_size: n })}
        />
      </section>
    </>
  )
}

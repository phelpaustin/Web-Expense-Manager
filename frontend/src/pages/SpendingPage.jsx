import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

// The two views are the old Bills and Expenses pages, each as its own chunk, shown under one title.
const ExpensesPage = lazy(() => import('./ExpensesPage.jsx'))
const BillsPage = lazy(() => import('./BillsPage.jsx'))

export const VIEWS = [
  { key: 'receipts', label: 'By receipt' },
  { key: 'items', label: 'All items' },
]
const STORE_KEY = 'spendingView'

// The last view you chose, so the page opens where you left it. Browser storage can be missing or
// blocked, so every use is wrapped and the page works without it.
function rememberedView() {
  try {
    return localStorage.getItem(STORE_KEY) === 'items' ? 'items' : 'receipts'
  } catch {
    return 'receipts'
  }
}
function remember(view) {
  try {
    localStorage.setItem(STORE_KEY, view)
  } catch {
    /* not available: the choice just is not remembered */
  }
}

function AddMenu({ onExpense, onBill, onReceipt }) {
  const [open, setOpen] = useState(false)
  const pick = (fn) => () => {
    setOpen(false)
    fn()
  }
  return (
    <div className="add-menu-wrap" onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}>
      <button type="button" className="add-menu-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        ➕ Add
      </button>
      {open && (
        <>
          <div className="notif-backdrop" onClick={() => setOpen(false)} />
          <div className="add-menu" role="menu" aria-label="Add">
            <button type="button" role="menuitem" onClick={pick(onExpense)}>
              <strong>Add expense</strong>
              <span>One purchase, quickly</span>
            </button>
            <button type="button" role="menuitem" onClick={pick(onBill)}>
              <strong>Add a bill with items</strong>
              <span>A shop trip with its lines</span>
            </button>
            <button type="button" role="menuitem" onClick={pick(onReceipt)}>
              <strong>Upload a receipt</strong>
              <span>A photo or PDF, itemise later</span>
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// Spending: every purchase in one place. "By receipt" lists bills with their receipts and what is left
// to itemise; "All items" lists the individual expenses, with search, filters and editing.
export default function SpendingPage({ bills, expenseProps }) {
  const [params, setParams] = useSearchParams()
  const asked = params.get('view')
  const view = asked === 'items' || asked === 'receipts' ? asked : rememberedView()
  const adding = params.get('add')
  const fileInput = useRef(null)

  function go(nextView, add) {
    const next = new URLSearchParams(params)
    next.set('view', nextView)
    if (add) next.set('add', add)
    else next.delete('add')
    setParams(next, { replace: true })
  }
  function choose(nextView) {
    remember(nextView)
    go(nextView)
  }

  // Expenses changed on the other view (a bill's items edited, an expense deleted) can leave the list of
  // bills out of date, so it is read again whenever you come back to it.
  const first = useRef(true)
  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    if (view === 'receipts') bills.reload?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view])

  async function uploadReceipt(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    go('receipts')
    await bills.actions.uploadBill(file)
  }

  return (
    <>
      <div className="spending-head">
        <h1 className="page-title">🧾 Spending</h1>
        <AddMenu
          onExpense={() => go('items')}
          onBill={() => go('items', 'bill')}
          onReceipt={() => fileInput.current?.click()}
        />
        <input
          ref={fileInput}
          type="file"
          aria-label="Receipt file"
          accept="application/pdf,image/*"
          onChange={uploadReceipt}
          hidden
        />
      </div>

      <div className="tabs" role="group" aria-label="View">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            aria-pressed={view === v.key}
            className={view === v.key ? 'tab active' : 'tab'}
            onClick={() => choose(v.key)}
          >
            {v.label}
          </button>
        ))}
      </div>

      <Suspense fallback={<p className="subtitle">Loading…</p>}>
        {view === 'receipts' ? (
          <BillsPage embedded state={bills} options={expenseProps.options} />
        ) : (
          <ExpensesPage
            // Adding a bill with items opens the form already in bill mode, so a fresh page is needed for it.
            key={adding === 'bill' ? 'bill' : 'plain'}
            embedded
            initialBillMode={adding === 'bill'}
            {...expenseProps}
          />
        )}
      </Suspense>
    </>
  )
}

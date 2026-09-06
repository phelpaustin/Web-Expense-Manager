import { money } from '../format.js'

export default function BillsPage({
  pendingBills,
  pendingForm,
  setPendingForm,
  onAddPending,
  onItemise,
  onDeletePending,
  onUploadReceipt,
  onUploadBill,
  onBulkUploadBills,
  bulkImportNotice,
  onDismissBulkNotice,
  onDismissDuplicate,
  onViewReceipt,
  onDeleteReceipt,
  ledger,
  manualForm,
  setManualForm,
  onAddManual,
  onDeleteManual,
}) {
  return (
    <>
      <h1 className="page-title">📒 Bills</h1>

      <section className="panel">
        <h2>🧾 Pending bills</h2>
        <div className="upload-bill">
          <label className="btn-upload">
            📤 Upload bill (PDF or photo)
            <input
              type="file"
              accept="application/pdf,image/*"
              onChange={(e) => {
                const f = e.target.files[0]
                if (f) onUploadBill(f)
                e.target.value = ''
              }}
            />
          </label>
          <label className="btn-upload btn-upload-bulk">
            📊 Bulk import from bank statement
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => {
                const f = e.target.files[0]
                if (f) onBulkUploadBills(f)
                e.target.value = ''
              }}
            />
          </label>
          <span className="subtitle">Attach a receipt now and itemise it later.</span>
        </div>
        {bulkImportNotice && (
          <div className="notice">
            <p>
              Imported {bulkImportNotice.created} bill(s)
              {bulkImportNotice.possible_duplicates > 0 &&
                ` — ${bulkImportNotice.possible_duplicates} flagged as possible duplicates, please review below`}
              {bulkImportNotice.skipped?.length > 0 && ` — ${bulkImportNotice.skipped.length} row(s) skipped`}
              .
            </p>
            {bulkImportNotice.skipped?.length > 0 && (
              <ul className="notice-details">
                {bulkImportNotice.skipped.map((s) => (
                  <li key={s.row}>
                    Row {s.row}: {s.reason}
                  </li>
                ))}
              </ul>
            )}
            <button className="icon-btn" onClick={onDismissBulkNotice} title="Dismiss">
              ✕
            </button>
          </div>
        )}
        <form className="add-form" onSubmit={onAddPending}>
          <input
            type="date"
            required
            value={pendingForm.date}
            onChange={(e) => setPendingForm({ ...pendingForm, date: e.target.value })}
          />
          <input
            type="text"
            placeholder="Shop"
            required
            value={pendingForm.shop}
            onChange={(e) => setPendingForm({ ...pendingForm, shop: e.target.value })}
          />
          <input
            type="text"
            placeholder="Note (optional)"
            value={pendingForm.note}
            onChange={(e) => setPendingForm({ ...pendingForm, note: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={pendingForm.amount}
            onChange={(e) => setPendingForm({ ...pendingForm, amount: e.target.value })}
          />
          <button type="submit">Add</button>
        </form>

        {pendingBills.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Shop</th>
                <th>Note</th>
                <th className="right">Amount</th>
                <th>Receipt</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pendingBills.map((b) => (
                <tr key={b.id} className={b.possible_duplicate ? 'row-flagged' : ''}>
                  <td>
                    {b.date}
                    {b.possible_duplicate && (
                      <span className="duplicate-badge" title="Same date/amount as an existing bill — please verify">
                        ⚠ possible duplicate
                      </span>
                    )}
                  </td>
                  <td>{b.shop}</td>
                  <td>{b.note}</td>
                  <td className="right">{money(b.amount)}</td>
                  <td className="nowrap">
                    {b.has_receipt && (
                      <>
                        <button className="icon-btn" onClick={() => onViewReceipt(b.id)} title="View receipt">
                          👁
                        </button>
                        <button className="delete-btn" onClick={() => onDeleteReceipt(b.id)} title="Remove receipt">
                          ✕
                        </button>
                      </>
                    )}
                    <label className="icon-btn file-attach" title="Attach PDF or image">
                      📎
                      <input
                        type="file"
                        accept="application/pdf,image/*"
                        onChange={(e) => {
                          const f = e.target.files[0]
                          if (f) onUploadReceipt(b.id, f)
                          e.target.value = ''
                        }}
                      />
                    </label>
                  </td>
                  <td className="right nowrap">
                    {b.possible_duplicate && (
                      <button
                        className="icon-btn"
                        onClick={() => onDismissDuplicate(b.id)}
                        title="Not a duplicate — clear flag"
                      >
                        ✔
                      </button>
                    )}
                    <button className="icon-btn" onClick={() => onItemise(b.id)} title="Itemise into an expense">
                      ✓
                    </button>
                    <button className="delete-btn" onClick={() => onDeletePending(b.id)} title="Delete">
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>📒 Bills ledger</h2>
        <p className="subtitle">Consolidated, de-duplicated view of expenses, pending, and manual bills.</p>
        <form className="add-form" onSubmit={onAddManual}>
          <input
            type="date"
            required
            value={manualForm.date}
            onChange={(e) => setManualForm({ ...manualForm, date: e.target.value })}
          />
          <input
            type="text"
            placeholder="Shop (manual entry)"
            required
            value={manualForm.shop}
            onChange={(e) => setManualForm({ ...manualForm, shop: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={manualForm.amount}
            onChange={(e) => setManualForm({ ...manualForm, amount: e.target.value })}
          />
          <button type="submit">Add manual</button>
        </form>

        {ledger.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Shop</th>
                <th>Source</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((r, idx) => (
                <tr key={`${r.source}-${r.id ?? idx}`}>
                  <td>{r.date}</td>
                  <td>{r.shop}</td>
                  <td>
                    <span className={`source-badge source-${r.source.toLowerCase()}`}>{r.source}</span>
                  </td>
                  <td className="right">{money(r.amount)}</td>
                  <td className="right nowrap">
                    {r.source === 'Manual' && (
                      <button className="delete-btn" onClick={() => onDeleteManual(r.id)} title="Delete manual entry">
                        ✕
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  )
}

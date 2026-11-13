import CurrencySelect from '../components/CurrencySelect.jsx'
import { money } from '../format.js'

export default function IncomePage({
  income,
  incomeSummary,
  incomeForm,
  setIncomeForm,
  savingIncome,
  editingIncomeId = null,
  onEditIncome,
  onCancelEditIncome,
  onAddIncome,
  onDeleteIncome,
  currencies = [],
  baseCurrency,
}) {
  const editing = editingIncomeId !== null

  return (
    <>
      <h1 className="page-title">💵 Income</h1>

      {incomeSummary && (
        <section className="cards">
          <div className="card">
            <span className="card-label">Income this month</span>
            <span className="card-value">{money(incomeSummary.this_month)}</span>
          </div>
          <div className="card">
            <span className="card-label">Avg income / month</span>
            <span className="card-value">{money(incomeSummary.avg_month)}</span>
          </div>
          <div className="card">
            <span className="card-label">Total income</span>
            <span className="card-value">{money(incomeSummary.total)}</span>
          </div>
        </section>
      )}

      <section className="panel">
        <h2>{editing ? '✏️ Edit income' : '➕ Add income'}</h2>
        <form className="add-form" onSubmit={onAddIncome}>
          <input
            type="date"
            aria-label="Date"
            required
            value={incomeForm.date}
            onChange={(e) => setIncomeForm({ ...incomeForm, date: e.target.value })}
          />
          <input
            type="text"
            aria-label="Source"
            placeholder="Source (e.g. Salary)"
            required
            value={incomeForm.source}
            onChange={(e) => setIncomeForm({ ...incomeForm, source: e.target.value })}
          />
          <input
            type="text"
            aria-label="Note"
            placeholder="Note (optional)"
            value={incomeForm.note}
            onChange={(e) => setIncomeForm({ ...incomeForm, note: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            aria-label="Amount"
            placeholder="Amount"
            required
            value={incomeForm.amount}
            onChange={(e) => setIncomeForm({ ...incomeForm, amount: e.target.value })}
          />
          <CurrencySelect
            value={incomeForm.currency}
            onChange={(c) => setIncomeForm({ ...incomeForm, currency: c })}
            currencies={currencies}
            defaultCurrency={baseCurrency}
          />
          <button type="submit" disabled={savingIncome}>
            {savingIncome ? 'Saving…' : editing ? 'Save' : 'Add'}
          </button>
          {editing && (
            <button type="button" className="ghost-btn" onClick={onCancelEditIncome}>
              Cancel
            </button>
          )}
        </form>

        {income.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Source</th>
                <th>Note</th>
                <th className="right">Amount</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {income.map((i) => (
                <tr key={i.id} className={i.id === editingIncomeId ? 'editing' : undefined}>
                  <td>{i.date}</td>
                  <td>{i.source}</td>
                  <td>{i.note}</td>
                  <td className="right">{money(i.amount, i.currency)}</td>
                  <td className="right">
                    <button
                      className="icon-btn"
                      onClick={() => {
                        onEditIncome(i)
                        window.scrollTo?.({ top: 0, behavior: 'smooth' })
                      }}
                      title="Edit"
                      aria-label={`Edit income ${i.source}`}
                    >
                      ✎
                    </button>{' '}
                    <button className="delete-btn" onClick={() => onDeleteIncome(i.id)} title="Delete" aria-label={`Delete income ${i.source}`}>
                      ✕
                    </button>
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

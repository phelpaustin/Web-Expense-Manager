export default function IncomePage({
  income,
  incomeSummary,
  incomeForm,
  setIncomeForm,
  savingIncome,
  onAddIncome,
  onDeleteIncome,
}) {
  return (
    <>
      <h1 className="page-title">💵 Income</h1>

      {incomeSummary && (
        <section className="cards">
          <div className="card">
            <span className="card-label">Income this month</span>
            <span className="card-value">${incomeSummary.this_month.toFixed(2)}</span>
          </div>
          <div className="card">
            <span className="card-label">Avg income / month</span>
            <span className="card-value">${incomeSummary.avg_month.toFixed(2)}</span>
          </div>
          <div className="card">
            <span className="card-label">Total income</span>
            <span className="card-value">${incomeSummary.total.toFixed(2)}</span>
          </div>
        </section>
      )}

      <section className="panel">
        <h2>➕ Add income</h2>
        <form className="add-form" onSubmit={onAddIncome}>
          <input
            type="date"
            required
            value={incomeForm.date}
            onChange={(e) => setIncomeForm({ ...incomeForm, date: e.target.value })}
          />
          <input
            type="text"
            placeholder="Source (e.g. Salary)"
            required
            value={incomeForm.source}
            onChange={(e) => setIncomeForm({ ...incomeForm, source: e.target.value })}
          />
          <input
            type="text"
            placeholder="Note (optional)"
            value={incomeForm.note}
            onChange={(e) => setIncomeForm({ ...incomeForm, note: e.target.value })}
          />
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            required
            value={incomeForm.amount}
            onChange={(e) => setIncomeForm({ ...incomeForm, amount: e.target.value })}
          />
          <button type="submit" disabled={savingIncome}>
            {savingIncome ? 'Saving…' : 'Add'}
          </button>
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
                <tr key={i.id}>
                  <td>{i.date}</td>
                  <td>{i.source}</td>
                  <td>{i.note}</td>
                  <td className="right">${i.amount.toFixed(2)}</td>
                  <td className="right">
                    <button className="delete-btn" onClick={() => onDeleteIncome(i.id)} title="Delete">
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

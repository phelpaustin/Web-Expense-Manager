import { useRef, useState } from 'react'
import { downloadBackup, restoreBackup } from '../api/client.js'

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

function summary(r) {
  const parts = [plural(r.expenses, 'expense'), plural(r.bills, 'bill')]
  if (r.receipts) parts.push(plural(r.receipts, 'receipt'))
  if (r.income) parts.push(`${r.income} income`)
  if (r.budgets) parts.push(plural(r.budgets, 'budget'))
  if (r.recurring) parts.push(`${r.recurring} recurring`)
  if (r.savings_goals) parts.push(plural(r.savings_goals, 'savings goal'))
  return parts.join(', ')
}

// Settings → App data: one file with everything the account owns (bills stay bills, receipts
// included), and the way back into an empty account.
export default function BackupPanel({ onError, onRestored = () => window.location.reload() }) {
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  async function download() {
    setBusy(true)
    try {
      await downloadBackup()
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function restore(e) {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) return
    setBusy(true)
    setResult(null)
    try {
      setResult(await restoreBackup(file))
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h2>Full backup</h2>
      <p className="muted-note">
        One file with everything in this account: expenses with the bills they belong to, receipts, budgets,
        income, recurring items, savings goals and settings. Expense Spaces are not included. Keep it somewhere
        safe; it is the way to move to another installation.
      </p>
      <div className="add-form">
        <button type="button" className="ghost-btn" disabled={busy} onClick={download}>
          Download full backup
        </button>
      </div>

      <h3>Restore a backup</h3>
      <p className="muted-note">
        Works only in an account that has no expenses, bills, budgets, income, recurring items or savings goals
        yet, so nothing is ever mixed or overwritten. Register a new account, then restore here.
      </p>
      {result ? (
        <div className="ok-note" role="status">
          Restored {summary(result)}.{' '}
          <button type="button" className="ghost-btn" onClick={onRestored}>
            Show my data
          </button>
        </div>
      ) : (
        <form className="add-form" onSubmit={restore}>
          <input ref={fileRef} type="file" accept=".zip,application/zip" aria-label="Backup file" />
          <button type="submit" className="ghost-btn" disabled={busy}>
            {busy ? 'Restoring…' : 'Restore backup'}
          </button>
        </form>
      )}
    </section>
  )
}

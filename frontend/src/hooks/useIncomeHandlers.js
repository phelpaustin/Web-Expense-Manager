import { useState } from 'react'
import { createIncome, deleteIncome } from '../api/client.js'

const EMPTY_INCOME = { date: '', source: '', note: '', amount: '', currency: '' }

export function useIncomeHandlers(loadAll, setError) {
  const [incomeForm, setIncomeForm] = useState(EMPTY_INCOME)
  const [savingIncome, setSavingIncome] = useState(false)

  async function handleAddIncome(e) {
    e.preventDefault()
    setSavingIncome(true)
    try {
      await createIncome({
        date: incomeForm.date,
        amount: parseFloat(incomeForm.amount),
        source: incomeForm.source,
        note: incomeForm.note,
        currency: incomeForm.currency || undefined,
      })
      setIncomeForm(EMPTY_INCOME)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingIncome(false)
    }
  }

  async function handleDeleteIncome(id) {
    try {
      await deleteIncome(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return { incomeForm, setIncomeForm, savingIncome, handleAddIncome, handleDeleteIncome }
}

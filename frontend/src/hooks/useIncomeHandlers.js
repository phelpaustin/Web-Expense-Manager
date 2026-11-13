import { useState } from 'react'
import { createIncome, deleteIncome, updateIncome } from '../api/client.js'
import { PART } from './useAppData.js'
import { positiveAmount } from './useExpenseHandlers.js'

const EMPTY_INCOME = { date: '', source: '', note: '', amount: '', currency: '' }

// Income feeds the dashboard's savings figures but nothing else.
const INCOME_PARTS = [PART.INCOME, PART.DASHBOARD]

export function useIncomeHandlers(loadAll, setError) {
  const [incomeForm, setIncomeForm] = useState(EMPTY_INCOME)
  const [savingIncome, setSavingIncome] = useState(false)
  // The id of the entry being edited, or null while the form adds a new one.
  const [editingIncomeId, setEditingIncomeId] = useState(null)

  function startEditIncome(row) {
    setEditingIncomeId(row.id)
    setIncomeForm({
      date: row.date || '',
      source: row.source || '',
      note: row.note || '',
      amount: String(row.amount ?? ''),
      currency: row.currency || '',
    })
  }

  function cancelEditIncome() {
    setEditingIncomeId(null)
    setIncomeForm(EMPTY_INCOME)
  }

  async function handleAddIncome(e) {
    e.preventDefault()
    const amount = positiveAmount(incomeForm.amount)
    if (amount === null) {
      setError('Enter an amount greater than zero')
      return
    }
    setSavingIncome(true)
    try {
      const entry = {
        date: incomeForm.date,
        amount,
        source: incomeForm.source,
        note: incomeForm.note,
        currency: incomeForm.currency || undefined,
      }
      if (editingIncomeId !== null) await updateIncome(editingIncomeId, entry)
      else await createIncome(entry)
      setEditingIncomeId(null)
      setIncomeForm(EMPTY_INCOME)
      await loadAll(INCOME_PARTS)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingIncome(false)
    }
  }

  async function handleDeleteIncome(id) {
    try {
      await deleteIncome(id)
      if (id === editingIncomeId) cancelEditIncome()
      await loadAll(INCOME_PARTS)
    } catch (err) {
      setError(err.message)
    }
  }

  return {
    incomeForm,
    setIncomeForm,
    savingIncome,
    editingIncomeId,
    startEditIncome,
    cancelEditIncome,
    handleAddIncome,
    handleDeleteIncome,
  }
}

import { useState } from 'react'
import { createRecurring, updateRecurring, deleteRecurring, backfillRecurring, applyRecurring, applyDueRecurring } from '../api/client.js'

const EMPTY_RECURRING = { item: '', category: '', amount: '', frequency: 'Monthly', auto_post: false }

export function useRecurringHandlers(loadAll, setError) {
  const [recurringForm, setRecurringForm] = useState(EMPTY_RECURRING)
  const [savingRecurring, setSavingRecurring] = useState(false)

  async function handleAddRecurring(e) {
    e.preventDefault()
    setSavingRecurring(true)
    try {
      await createRecurring({
        item: recurringForm.item,
        category: recurringForm.category,
        amount: parseFloat(recurringForm.amount),
        frequency: recurringForm.frequency,
        auto_post: recurringForm.auto_post,
      })
      setRecurringForm(EMPTY_RECURRING)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingRecurring(false)
    }
  }

  async function handleApplyRecurring(id) {
    try {
      await applyRecurring(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleApplyDue() {
    try {
      await applyDueRecurring()
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteRecurring(id) {
    try {
      await deleteRecurring(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateRecurring(id, changes) {
    try {
      await updateRecurring(id, changes)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleBackfillRecurring(id, entry) {
    try {
      await backfillRecurring(id, entry)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return {
    recurringForm,
    setRecurringForm,
    savingRecurring,
    handleAddRecurring,
    handleApplyRecurring,
    handleApplyDue,
    handleDeleteRecurring,
    handleUpdateRecurring,
    handleBackfillRecurring,
  }
}

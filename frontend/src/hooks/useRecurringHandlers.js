import { useRef, useState } from 'react'
import { createRecurring, updateRecurring, deleteRecurring, backfillRecurring, applyRecurring, applyDueRecurring } from '../api/client.js'
import { EXPENSE_PARTS, PART } from './useAppData.js'

const EMPTY_RECURRING = { item: '', category: '', amount: '', currency: '', frequency: 'Monthly', auto_post: false }

// Editing a template changes only the template; posting or back-filling creates expenses.
const POSTING_PARTS = [PART.RECURRING, ...EXPENSE_PARTS]

export function useRecurringHandlers(loadAll, setError) {
  const [recurringForm, setRecurringForm] = useState(EMPTY_RECURRING)
  const [savingRecurring, setSavingRecurring] = useState(false)
  // Applies still running. Each one posts real expenses, so a second click (or a
  // double click) while one is in flight must not start another. A ref, not state,
  // because two clicks can land before React re-renders.
  const applying = useRef(new Set())

  async function runOnce(key, action) {
    if (applying.current.has(key)) return
    applying.current.add(key)
    try {
      await action()
      await loadAll(POSTING_PARTS)
    } catch (err) {
      setError(err.message)
    } finally {
      applying.current.delete(key)
    }
  }

  async function handleAddRecurring(e) {
    e.preventDefault()
    setSavingRecurring(true)
    try {
      await createRecurring({
        item: recurringForm.item,
        category: recurringForm.category,
        amount: parseFloat(recurringForm.amount),
        currency: recurringForm.currency || undefined,
        frequency: recurringForm.frequency,
        auto_post: recurringForm.auto_post,
      })
      setRecurringForm(EMPTY_RECURRING)
      await loadAll([PART.RECURRING])
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingRecurring(false)
    }
  }

  function handleApplyRecurring(id) {
    return runOnce(`apply:${id}`, () => applyRecurring(id))
  }

  function handleApplyDue() {
    return runOnce('apply-due', () => applyDueRecurring())
  }

  async function handleDeleteRecurring(id) {
    try {
      await deleteRecurring(id)
      await loadAll([PART.RECURRING])
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateRecurring(id, changes) {
    try {
      await updateRecurring(id, changes)
      await loadAll([PART.RECURRING])
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleBackfillRecurring(id, entry) {
    try {
      await backfillRecurring(id, entry)
      await loadAll(POSTING_PARTS)
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

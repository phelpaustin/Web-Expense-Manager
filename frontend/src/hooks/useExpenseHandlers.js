import { useState } from 'react'
import { createExpense, createExpensesBulk, updateExpense, deleteExpense, importExpenses, exportExpenses } from '../api/client.js'

const EMPTY_FORM = {
  date: '',
  category: '',
  subcategory: '',
  description: '',
  amount: '',
  quantity: '1',
  unit: 'Count',
  shop: '',
  brand: '',
  currency: '', // '' = let the server default it (space currency, else base currency)
  trip_id: '',
  group_id: '',
}

// A positive finite number, or null. Guards against sending NaN (which JSON turns into null).
export function positiveAmount(value) {
  const n = parseFloat(value)
  return Number.isFinite(n) && n > 0 ? n : null
}

export function useExpenseHandlers(loadAll, setError) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [importCurrency, setImportCurrency] = useState('')

  async function handleAdd(e) {
    e.preventDefault()
    const amount = positiveAmount(form.amount)
    if (amount === null) {
      setError('Enter an amount greater than zero')
      return
    }
    setSaving(true)
    try {
      await createExpense({
        date: form.date,
        category: form.category,
        subcategory: form.subcategory,
        description: form.description,
        amount,
        quantity: parseFloat(form.quantity) || 1,
        unit: form.unit || 'Count',
        shop: form.shop,
        brand: form.brand,
        currency: form.currency || undefined,
        trip_id: form.trip_id ? parseInt(form.trip_id, 10) : null,
        group_id: form.group_id ? parseInt(form.group_id, 10) : null,
      })
      setForm(EMPTY_FORM)
      await loadAll()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    try {
      await deleteExpense(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleImport(file) {
    const result = await importExpenses(file, importCurrency)
    await loadAll()
    return result
  }

  async function handleAddRow(payload) {
    await createExpense(payload)
    await loadAll()
  }

  async function handleAddBill(items) {
    await createExpensesBulk(items)
    await loadAll()
  }

  function handleExport(format) {
    return exportExpenses(format).catch((err) => setError(err.message))
  }

  function startEdit(expense) {
    setEditingId(expense.id)
    setEditForm({
      date: expense.date,
      category: expense.category,
      subcategory: expense.subcategory || '',
      description: expense.description,
      amount: String(expense.amount),
      quantity: String(expense.quantity ?? 1),
      unit: expense.unit || 'Count',
      shop: expense.shop || '',
      currency: expense.currency || '',
      group_id: expense.group_id ? String(expense.group_id) : '',
    })
  }

  function cancelEdit() {
    setEditingId(null)
    setEditForm(EMPTY_FORM)
  }

  async function saveEdit(id) {
    const amount = positiveAmount(editForm.amount)
    if (amount === null) {
      setError('Enter an amount greater than zero')
      return
    }
    try {
      await updateExpense(id, {
        date: editForm.date,
        category: editForm.category,
        subcategory: editForm.subcategory,
        description: editForm.description,
        amount,
        quantity: parseFloat(editForm.quantity) || 1,
        unit: editForm.unit || 'Count',
        shop: editForm.shop,
        currency: editForm.currency || undefined,
        group_id: editForm.group_id ? parseInt(editForm.group_id, 10) : null,
      })
      cancelEdit()
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return {
    form,
    setForm,
    saving,
    editingId,
    editForm,
    setEditForm,
    importCurrency,
    setImportCurrency,
    handleAdd,
    handleDelete,
    handleImport,
    handleAddRow,
    handleAddBill,
    handleExport,
    startEdit,
    cancelEdit,
    saveEdit,
  }
}

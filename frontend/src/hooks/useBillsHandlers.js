import { useState } from 'react'
import {
  createPendingBill,
  deletePendingBill,
  itemisePendingBill,
  uploadReceipt,
  uploadBill,
  bulkUploadPendingBills,
  dismissDuplicate,
  viewReceipt,
  deleteReceipt,
  createManualBill,
  deleteManualBill,
} from '../api/client.js'

const EMPTY_BILL = { date: '', shop: '', amount: '', note: '' }

// pendingBills is passed in (rather than fetched here) so handleItemise can
// look up whether a bill already has an amount before prompting for one.
export function useBillsHandlers(loadAll, setError, pendingBills) {
  const [pendingForm, setPendingForm] = useState(EMPTY_BILL)
  const [manualForm, setManualForm] = useState(EMPTY_BILL)
  const [bulkImportNotice, setBulkImportNotice] = useState(null)

  async function handleAddPending(e) {
    e.preventDefault()
    try {
      await createPendingBill({
        date: pendingForm.date,
        shop: pendingForm.shop,
        amount: parseFloat(pendingForm.amount),
        note: pendingForm.note,
      })
      setPendingForm(EMPTY_BILL)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleItemise(id) {
    try {
      const bill = pendingBills.find((b) => b.id === id)
      let amount
      if (!bill || !bill.amount) {
        const entered = window.prompt('Amount for this bill?', '')
        if (entered === null) return
        const parsed = parseFloat(entered)
        if (!Number.isFinite(parsed) || parsed <= 0) {
          setError('Please enter a valid amount to itemise this bill.')
          return
        }
        amount = parsed
      }
      await itemisePendingBill(id, amount)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeletePending(id) {
    try {
      await deletePendingBill(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUploadReceipt(id, file) {
    try {
      await uploadReceipt(id, file)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUploadBill(file) {
    try {
      await uploadBill(file)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleBulkUploadBills(file) {
    try {
      const result = await bulkUploadPendingBills(file)
      setBulkImportNotice(result)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDismissDuplicate(id) {
    try {
      await dismissDuplicate(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  function handleViewReceipt(id) {
    viewReceipt(id).catch((err) => setError(err.message))
  }

  async function handleDeleteReceipt(id) {
    try {
      await deleteReceipt(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddManual(e) {
    e.preventDefault()
    try {
      await createManualBill({
        date: manualForm.date,
        shop: manualForm.shop,
        amount: parseFloat(manualForm.amount),
        note: manualForm.note,
      })
      setManualForm(EMPTY_BILL)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteManual(id) {
    try {
      await deleteManualBill(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return {
    pendingForm,
    setPendingForm,
    manualForm,
    setManualForm,
    bulkImportNotice,
    setBulkImportNotice,
    handleAddPending,
    handleItemise,
    handleDeletePending,
    handleUploadReceipt,
    handleUploadBill,
    handleBulkUploadBills,
    handleDismissDuplicate,
    handleViewReceipt,
    handleDeleteReceipt,
    handleAddManual,
    handleDeleteManual,
  }
}

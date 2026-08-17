import { useEffect, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import {
  fetchExpenses,
  fetchSummary,
  fetchTrends,
  fetchCategories,
  fetchBudgetStatus,
  createExpense,
  updateExpense,
  deleteExpense,
  setBudget,
  deleteBudget,
  fetchIncome,
  fetchIncomeSummary,
  createIncome,
  deleteIncome,
  fetchRecurring,
  createRecurring,
  deleteRecurring,
  applyRecurring,
  applyDueRecurring,
  fetchPendingBills,
  createPendingBill,
  deletePendingBill,
  itemisePendingBill,
  fetchLedger,
  createManualBill,
  deleteManualBill,
  fetchOptions,
  fetchMe,
  getToken,
  logout,
} from './api/client.js'
import AuthScreen from './AuthScreen.jsx'
import Layout from './Layout.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ExpensesPage from './pages/ExpensesPage.jsx'
import IncomePage from './pages/IncomePage.jsx'
import RecurringPage from './pages/RecurringPage.jsx'
import BillsPage from './pages/BillsPage.jsx'

const EMPTY_FORM = { date: '', category: '', subcategory: '', description: '', amount: '', quantity: '1', unit: 'Count', shop: '', brand: '', currency: 'SEK' }
const EMPTY_INCOME = { date: '', source: '', note: '', amount: '' }
const EMPTY_RECURRING = { item: '', category: '', amount: '', frequency: 'Monthly', auto_post: false }
const EMPTY_BILL = { date: '', shop: '', amount: '', note: '' }
const EMPTY_OPTIONS = { categories: [], subcategories: {}, units: [], shops: [] }

export default function App() {
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [expenses, setExpenses] = useState([])
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState(null)
  const [categories, setCategories] = useState([])
  const [budgets, setBudgets] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(EMPTY_FORM)
  const [income, setIncome] = useState([])
  const [incomeSummary, setIncomeSummary] = useState(null)
  const [incomeForm, setIncomeForm] = useState(EMPTY_INCOME)
  const [savingIncome, setSavingIncome] = useState(false)
  const [recurring, setRecurring] = useState([])
  const [recurringForm, setRecurringForm] = useState(EMPTY_RECURRING)
  const [savingRecurring, setSavingRecurring] = useState(false)
  const [pendingBills, setPendingBills] = useState([])
  const [pendingForm, setPendingForm] = useState(EMPTY_BILL)
  const [ledger, setLedger] = useState([])
  const [manualForm, setManualForm] = useState(EMPTY_BILL)
  const [options, setOptions] = useState(EMPTY_OPTIONS)

  function loadAll() {
    return Promise.all([
      fetchExpenses(),
      fetchSummary(),
      fetchTrends(),
      fetchCategories(),
      fetchBudgetStatus(),
      fetchIncome(),
      fetchIncomeSummary(),
      fetchRecurring(),
      fetchPendingBills(),
      fetchLedger(),
      fetchOptions(),
    ])
      .then(([exp, sum, tr, cat, bud, inc, incSum, rec, pend, led, opts]) => {
        setExpenses(exp)
        setSummary(sum)
        setTrends(tr)
        setCategories(cat)
        setBudgets(bud)
        setIncome(inc)
        setIncomeSummary(incSum)
        setRecurring(rec)
        setPendingBills(pend)
        setLedger(led)
        setOptions(opts)
        setError(null)
      })
      .catch((err) => setError(err.message))
  }

  // On mount, if a token exists, verify it and load the user's data.
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true)
      setLoading(false)
      return
    }
    fetchMe()
      .then((me) => {
        setUser(me)
        return loadAll()
      })
      .catch(() => {
        logout()
      })
      .finally(() => {
        setAuthChecked(true)
        setLoading(false)
      })
  }, [])

  function handleAuthed() {
    setLoading(true)
    fetchMe()
      .then((me) => {
        setUser(me)
        return loadAll()
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  function handleLogout() {
    logout()
    setUser(null)
    setExpenses([])
    setSummary(null)
    setTrends(null)
    setCategories([])
    setBudgets([])
    setIncome([])
    setIncomeSummary(null)
    setRecurring([])
    setPendingBills([])
    setLedger([])
    setOptions(EMPTY_OPTIONS)
  }

  async function handleAdd(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await createExpense({
        date: form.date,
        category: form.category,
        subcategory: form.subcategory,
        description: form.description,
        amount: parseFloat(form.amount),
        quantity: parseFloat(form.quantity) || 1,
        unit: form.unit || 'Count',
        shop: form.shop,
        brand: form.brand,
        currency: form.currency || 'SEK',
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
    })
  }

  function cancelEdit() {
    setEditingId(null)
    setEditForm(EMPTY_FORM)
  }

  async function saveEdit(id) {
    try {
      await updateExpense(id, {
        date: editForm.date,
        category: editForm.category,
        subcategory: editForm.subcategory,
        description: editForm.description,
        amount: parseFloat(editForm.amount),
        quantity: parseFloat(editForm.quantity) || 1,
        unit: editForm.unit || 'Count',
        shop: editForm.shop,
      })
      cancelEdit()
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSetBudget(category, amount) {
    const value = parseFloat(amount)
    if (!value || value <= 0) return
    try {
      await setBudget(category, value)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteBudget(category) {
    try {
      await deleteBudget(category)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddIncome(e) {
    e.preventDefault()
    setSavingIncome(true)
    try {
      await createIncome({
        date: incomeForm.date,
        amount: parseFloat(incomeForm.amount),
        source: incomeForm.source,
        note: incomeForm.note,
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
      await itemisePendingBill(id)
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

  if (!authChecked) {
    return (
      <div className="container">
        <p>Loading…</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="container">
        <AuthScreen onAuthed={handleAuthed} />
      </div>
    )
  }

  return (
    <Routes>
      <Route element={<Layout user={user} onLogout={handleLogout} error={error} loading={loading} />}>
        <Route
          index
          element={
            <DashboardPage
              summary={summary}
              incomeSummary={incomeSummary}
              budgets={budgets}
              trends={trends}
              categories={categories}
              onSetBudget={handleSetBudget}
              onDeleteBudget={handleDeleteBudget}
            />
          }
        />
        <Route
          path="expenses"
          element={
            <ExpensesPage
              expenses={expenses}
              form={form}
              setForm={setForm}
              saving={saving}
              onAdd={handleAdd}
              editingId={editingId}
              editForm={editForm}
              setEditForm={setEditForm}
              startEdit={startEdit}
              cancelEdit={cancelEdit}
              saveEdit={saveEdit}
              onDelete={handleDelete}
              options={options}
            />
          }
        />
        <Route
          path="income"
          element={
            <IncomePage
              income={income}
              incomeSummary={incomeSummary}
              incomeForm={incomeForm}
              setIncomeForm={setIncomeForm}
              savingIncome={savingIncome}
              onAddIncome={handleAddIncome}
              onDeleteIncome={handleDeleteIncome}
            />
          }
        />
        <Route
          path="recurring"
          element={
            <RecurringPage
              recurring={recurring}
              recurringForm={recurringForm}
              setRecurringForm={setRecurringForm}
              savingRecurring={savingRecurring}
              onAdd={handleAddRecurring}
              onApply={handleApplyRecurring}
              onApplyDue={handleApplyDue}
              onDelete={handleDeleteRecurring}
            />
          }
        />
        <Route
          path="bills"
          element={
            <BillsPage
              pendingBills={pendingBills}
              pendingForm={pendingForm}
              setPendingForm={setPendingForm}
              onAddPending={handleAddPending}
              onItemise={handleItemise}
              onDeletePending={handleDeletePending}
              ledger={ledger}
              manualForm={manualForm}
              setManualForm={setManualForm}
              onAddManual={handleAddManual}
              onDeleteManual={handleDeleteManual}
            />
          }
        />
      </Route>
    </Routes>
  )
}

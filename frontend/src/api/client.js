// Thin wrappers around the backend REST API.
// The /api prefix is proxied to FastAPI by Vite during development.
// In production, set VITE_API_URL to the deployed backend URL (e.g. https://api.example.com).

const API_BASE = import.meta.env.VITE_API_URL || ''

const TOKEN_KEY = 'expense_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY)
}

// Central fetch wrapper: attaches the auth header and normalizes errors.
async function request(path, options = {}) {
  const token = getToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    logout()
    throw new Error('Session expired — please log in again.')
  }
  if (!res.ok) {
    let message = 'Request failed'
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(message)
  }
  if (res.status === 204) return null
  return res.json()
}

// ── Auth ──────────────────────────────────────────────
export async function login(email, password) {
  // OAuth2 password flow expects form-encoded username/password.
  const body = new URLSearchParams({ username: email, password })
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!res.ok) throw new Error('Incorrect email or password')
  const data = await res.json()
  setToken(data.access_token)
  return data
}

export async function register(email, password, name) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  })
  if (!res.ok) {
    let message = 'Registration failed'
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // ignore
    }
    throw new Error(message)
  }
  const data = await res.json()
  setToken(data.access_token)
  return data
}

export async function googleLogin(credential) {
  const res = await fetch(`${API_BASE}/api/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  })
  if (!res.ok) {
    let message = 'Google sign-in failed'
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // ignore
    }
    throw new Error(message)
  }
  const data = await res.json()
  setToken(data.access_token)
  return data
}

export function fetchMe() {
  return request('/api/auth/me')
}

export function forgotPassword(email) {
  return request('/api/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
}

export function resetPassword(token, new_password) {
  return request('/api/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password }),
  })
}

export function deleteAccount(password) {
  return request('/api/auth/delete-account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
}

// ── Data ──────────────────────────────────────────────
export function fetchExpenses() {
  return request('/api/expenses')
}

export function fetchSummary() {
  return request('/api/expenses/summary')
}

export function fetchTrends() {
  return request('/api/analytics/trends')
}

export function fetchCategories() {
  return request('/api/analytics/categories')
}

export function fetchBudgetStatus() {
  return request('/api/budgets/status')
}

export function fetchMetrics() {
  return request('/api/metrics')
}

export function fetchBudgetConfig() {
  return request('/api/budgets/config')
}

export function fetchPeriodStatus() {
  return request('/api/budgets/period-status')
}

export function setBudgetConfig(period, rollover) {
  return request('/api/budgets/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period, rollover }),
  })
}

export function createExpense(expense) {
  return request('/api/expenses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(expense),
  })
}

export function updateExpense(id, changes) {
  return request(`/api/expenses/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  })
}

export function deleteExpense(id) {
  return request(`/api/expenses/${id}`, { method: 'DELETE' })
}

export function setBudget(category, amount) {
  return request('/api/budgets', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, amount }),
  })
}

export function deleteBudget(category) {
  return request(`/api/budgets/${encodeURIComponent(category)}`, { method: 'DELETE' })
}

export function fetchIncome() {
  return request('/api/income')
}

export function fetchIncomeSummary() {
  return request('/api/income/summary')
}

export function createIncome(entry) {
  return request('/api/income', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  })
}

export function deleteIncome(id) {
  return request(`/api/income/${id}`, { method: 'DELETE' })
}

export function fetchRecurring() {
  return request('/api/recurring')
}

export function createRecurring(template) {
  return request('/api/recurring', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(template),
  })
}

export function deleteRecurring(id) {
  return request(`/api/recurring/${id}`, { method: 'DELETE' })
}

export function applyRecurring(id) {
  return request(`/api/recurring/${id}/apply`, { method: 'POST' })
}

export function applyDueRecurring() {
  return request('/api/recurring/apply-due', { method: 'POST' })
}

export function fetchPendingBills() {
  return request('/api/pending-bills')
}

export function createPendingBill(bill) {
  return request('/api/pending-bills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bill),
  })
}

export function deletePendingBill(id) {
  return request(`/api/pending-bills/${id}`, { method: 'DELETE' })
}

export function itemisePendingBill(id) {
  return request(`/api/pending-bills/${id}/itemise`, { method: 'POST' })
}

export function fetchLedger() {
  return request('/api/bills-ledger')
}

export function createManualBill(bill) {
  return request('/api/bills-ledger/manual', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bill),
  })
}

export function deleteManualBill(id) {
  return request(`/api/bills-ledger/manual/${id}`, { method: 'DELETE' })
}

export function fetchOptions() {
  return request('/api/options')
}

export function changePassword(current_password, new_password) {
  return request('/api/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password, new_password }),
  })
}

export function addCategory(name) {
  return request('/api/options/category', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function deleteCategory(name) {
  return request(`/api/options/category/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function addSubcategory(category, name) {
  return request('/api/options/subcategory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, name }),
  })
}

export function deleteSubcategory(category, name) {
  return request(
    `/api/options/subcategory/${encodeURIComponent(category)}/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
  )
}

export function addUnit(name) {
  return request('/api/options/unit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function deleteUnit(name) {
  return request(`/api/options/unit/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function addShop(name) {
  return request('/api/options/shop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function deleteShop(name) {
  return request(`/api/options/shop/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function importExpenses(file, currencyOverride) {
  const body = new FormData()
  body.append('file', file)
  if (currencyOverride) body.append('currency_override', currencyOverride)
  // Note: no Content-Type header — the browser sets the multipart boundary.
  return request('/api/expenses/import', { method: 'POST', body })
}

export function setBaseCurrency(currency) {
  return request('/api/options/base-currency', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ currency }),
  })
}

export async function exportExpenses(format) {
  const token = getToken()
  const res = await fetch(`${API_BASE}/api/expenses/export?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error('Export failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = format === 'xlsx' ? 'expenses.xlsx' : 'expenses.csv'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

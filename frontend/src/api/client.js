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

export async function register(email, password) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
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

export function fetchMe() {
  return request('/api/auth/me')
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

import { useState } from 'react'
import {
  fetchSummary,
  fetchTrends,
  fetchCategories,
  fetchBudgetStatus,
  fetchIncome,
  fetchIncomeSummary,
  fetchRecurring,
  fetchPendingBills,
  fetchLedger,
  fetchOptions,
  fetchMetrics,
  fetchBudgetConfig,
  fetchPeriodStatus,
  fetchAlerts,
  fetchTrips,
  fetchGroups,
  saveDisplayCurrency,
} from '../api/client.js'
import { setDisplayCurrency } from '../format.js'

const EMPTY_OPTIONS = { categories: [], subcategories: {}, units: [], shops: [], base_currency: 'SEK', display_currency: 'SEK', currencies: [] }

// Owns every piece of data App.jsx fetches on load/mutation, plus the
// dashboard scope selector. Every domain handler hook calls loadAll() after a
// mutation to keep all pages in sync (simple, if a bit heavy-handed, refresh).
export function useAppData() {
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState(null)
  const [categories, setCategories] = useState([])
  const [budgets, setBudgets] = useState([])
  const [error, setError] = useState(null)
  const [income, setIncome] = useState([])
  const [incomeSummary, setIncomeSummary] = useState(null)
  const [recurring, setRecurring] = useState([])
  const [pendingBills, setPendingBills] = useState([])
  const [ledger, setLedger] = useState([])
  const [options, setOptions] = useState(EMPTY_OPTIONS)
  const [metrics, setMetrics] = useState(null)
  const [periodStatus, setPeriodStatus] = useState(null)
  const [budgetConfig, setBudgetConfigState] = useState({ period: 'Monthly', rollover: false })
  const [alerts, setAlerts] = useState([])
  const [trips, setTrips] = useState([])
  const [groups, setGroups] = useState([])
  const [dashboardScope, setDashboardScopeState] = useState('all')
  const [dashboardSpaceIds, setDashboardSpaceIdsState] = useState([])

  // Runs each loader independently. One failing endpoint (e.g. an FX problem
  // affecting only the converted dashboards) must not blank pages that don't
  // depend on it, so successful results are applied and failures are reported.
  function applySettled(tasks) {
    return Promise.allSettled(tasks.map((t) => t.load())).then((results) => {
      const failures = []
      results.forEach((res, i) => {
        if (res.status === 'fulfilled') tasks[i].apply(res.value)
        else failures.push(res.reason?.message || 'Request failed')
      })
      // De-duplicate so 8 identical 503s show one message.
      setError(failures.length ? [...new Set(failures)].join(' · ') : null)
    })
  }

  function loadAll() {
    const scope = dashboardScope
    const ids = dashboardSpaceIds
    return applySettled([
      { load: () => fetchSummary(scope, ids), apply: setSummary },
      { load: () => fetchTrends(scope, ids), apply: setTrends },
      { load: () => fetchCategories(scope, ids), apply: setCategories },
      { load: () => fetchBudgetStatus(scope, ids), apply: setBudgets },
      { load: () => fetchIncome(), apply: setIncome },
      { load: () => fetchIncomeSummary(), apply: setIncomeSummary },
      { load: () => fetchRecurring(), apply: setRecurring },
      { load: () => fetchPendingBills(), apply: setPendingBills },
      { load: () => fetchLedger(), apply: setLedger },
      {
        load: () => fetchOptions(),
        apply: (opts) => {
          setOptions(opts)
          setDisplayCurrency(opts.display_currency || opts.base_currency)
        },
      },
      { load: () => fetchMetrics(scope, ids), apply: setMetrics },
      { load: () => fetchBudgetConfig(), apply: setBudgetConfigState },
      { load: () => fetchPeriodStatus(scope, ids), apply: setPeriodStatus },
      { load: () => fetchAlerts(), apply: setAlerts },
      { load: () => fetchTrips(), apply: setTrips },
      { load: () => fetchGroups(), apply: setGroups },
    ])
  }

  // Re-fetch just the dashboard-relevant data scoped to "all", "personal", or one space.
  function handleSetDashboardScope(scope) {
    setDashboardScopeState(scope)
    setDashboardSpaceIdsState([])
    return applySettled([
      { load: () => fetchSummary(scope), apply: setSummary },
      { load: () => fetchTrends(scope), apply: setTrends },
      { load: () => fetchCategories(scope), apply: setCategories },
      { load: () => fetchBudgetStatus(scope), apply: setBudgets },
      { load: () => fetchMetrics(scope), apply: setMetrics },
      { load: () => fetchPeriodStatus(scope), apply: setPeriodStatus },
    ])
  }

  // Re-fetch scoped to a combined view across several chosen Expense Spaces.
  function handleSetDashboardSpaceIds(spaceIds) {
    setDashboardSpaceIdsState(spaceIds)
    return applySettled([
      { load: () => fetchSummary(null, spaceIds), apply: setSummary },
      { load: () => fetchTrends(null, spaceIds), apply: setTrends },
      { load: () => fetchCategories(null, spaceIds), apply: setCategories },
      { load: () => fetchBudgetStatus(null, spaceIds), apply: setBudgets },
      { load: () => fetchMetrics(null, spaceIds), apply: setMetrics },
      { load: () => fetchPeriodStatus(null, spaceIds), apply: setPeriodStatus },
    ])
  }

  // Clears every fetched data slice on logout (mirrors the pre-split behaviour —
  // alerts/trips/groups/dashboard scope are intentionally left as-is here too).
  function resetData() {
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
    setMetrics(null)
    setPeriodStatus(null)
  }

  // Switch the currency totals are shown in (null = follow the base currency).
  // Stored data is never changed, so this only needs a reload of the converted views.
  async function changeDisplayCurrency(code) {
    try {
      const updated = await saveDisplayCurrency(code || null)
      setOptions(updated)
      setDisplayCurrency(updated.display_currency || updated.base_currency)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return {
    changeDisplayCurrency,
    summary,
    trends,
    categories,
    budgets,
    error,
    setError,
    income,
    incomeSummary,
    recurring,
    pendingBills,
    ledger,
    options,
    setOptions,
    metrics,
    periodStatus,
    budgetConfig,
    alerts,
    trips,
    groups,
    dashboardScope,
    dashboardSpaceIds,
    loadAll,
    handleSetDashboardScope,
    handleSetDashboardSpaceIds,
    resetData,
  }
}

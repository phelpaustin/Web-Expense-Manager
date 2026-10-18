import { useRef, useState } from 'react'
import {
  fetchDashboard,
  fetchIncome,
  fetchIncomeSummary,
  fetchRecurring,
  fetchOptions,
  fetchBudgetConfig,
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
  const [options, setOptions] = useState(EMPTY_OPTIONS)
  const [metrics, setMetrics] = useState(null)
  const [periodStatus, setPeriodStatus] = useState(null)
  const [budgetConfig, setBudgetConfigState] = useState({ period: 'Monthly', rollover: false })
  const [alerts, setAlerts] = useState([])
  const [trips, setTrips] = useState([])
  const [groups, setGroups] = useState([])
  const [dashboardScope, setDashboardScopeState] = useState('all')
  const [dashboardSpaceIds, setDashboardSpaceIdsState] = useState([])
  // Bumped by resetData. A fetch that was already in flight when the user logged out
  // must not write its results into the next user's session.
  const sessionEpoch = useRef(0)

  // Runs each loader independently. One failing endpoint (e.g. an FX problem
  // affecting only the converted dashboards) must not blank pages that don't
  // depend on it, so successful results are applied and failures are reported.
  function applySettled(tasks) {
    const epoch = sessionEpoch.current
    return Promise.allSettled(tasks.map((t) => t.load())).then((results) => {
      if (epoch !== sessionEpoch.current) return
      const failures = []
      results.forEach((res, i) => {
        if (res.status === 'fulfilled') tasks[i].apply(res.value)
        else failures.push(res.reason?.message || 'Request failed')
      })
      // De-duplicate so 8 identical 503s show one message.
      setError(failures.length ? [...new Set(failures)].join(' · ') : null)
    })
  }

  // Spread one /api/dashboard response over the pieces of state the dashboard reads.
  // `alerts` is null when the request left them out (a scope change doesn't affect them).
  function applyDashboard(d) {
    setSummary(d.summary)
    setTrends(d.trends)
    setCategories(d.categories)
    setBudgets(d.budgets)
    setMetrics(d.metrics)
    setPeriodStatus(d.period_status)
    if (d.alerts) setAlerts(d.alerts)
  }

  function loadAll() {
    const scope = dashboardScope
    const ids = dashboardSpaceIds
    return applySettled([
      { load: () => fetchDashboard(scope, ids), apply: applyDashboard },
      { load: () => fetchIncome(), apply: setIncome },
      { load: () => fetchIncomeSummary(), apply: setIncomeSummary },
      { load: () => fetchRecurring(), apply: setRecurring },
      {
        load: () => fetchOptions(),
        apply: (opts) => {
          setOptions(opts)
          setDisplayCurrency(opts.display_currency || opts.base_currency)
        },
      },
      { load: () => fetchBudgetConfig(), apply: setBudgetConfigState },
      { load: () => fetchTrips(), apply: setTrips },
      { load: () => fetchGroups(), apply: setGroups },
    ])
  }

  // Re-fetch just the dashboard-relevant data scoped to "all", "personal", or one space.
  function handleSetDashboardScope(scope) {
    setDashboardScopeState(scope)
    setDashboardSpaceIdsState([])
    return applySettled([
      { load: () => fetchDashboard(scope, [], { includeAlerts: false }), apply: applyDashboard },
    ])
  }

  // Re-fetch scoped to a combined view across several chosen Expense Spaces.
  function handleSetDashboardSpaceIds(spaceIds) {
    setDashboardSpaceIdsState(spaceIds)
    return applySettled([
      { load: () => fetchDashboard(null, spaceIds, { includeAlerts: false }), apply: applyDashboard },
    ])
  }

  // Clears everything that belongs to the signed-in user, on logout or when the
  // session is rejected, so the next person to sign in on this browser starts clean.
  function resetData() {
    sessionEpoch.current += 1
    setSummary(null)
    setTrends(null)
    setCategories([])
    setBudgets([])
    setIncome([])
    setIncomeSummary(null)
    setRecurring([])
    setOptions(EMPTY_OPTIONS)
    setMetrics(null)
    setPeriodStatus(null)
    setBudgetConfigState({ period: 'Monthly', rollover: false })
    setAlerts([])
    setTrips([])
    setGroups([])
    setDashboardScopeState('all')
    setDashboardSpaceIdsState([])
    setError(null)
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

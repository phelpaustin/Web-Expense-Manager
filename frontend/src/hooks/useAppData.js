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
} from '../api/client.js'
import { setDisplayCurrency } from '../format.js'

const EMPTY_OPTIONS = { categories: [], subcategories: {}, units: [], shops: [], base_currency: 'SEK' }

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

  function loadAll() {
    return Promise.all([
      fetchSummary(dashboardScope, dashboardSpaceIds),
      fetchTrends(dashboardScope, dashboardSpaceIds),
      fetchCategories(dashboardScope, dashboardSpaceIds),
      fetchBudgetStatus(dashboardScope, dashboardSpaceIds),
      fetchIncome(),
      fetchIncomeSummary(),
      fetchRecurring(),
      fetchPendingBills(),
      fetchLedger(),
      fetchOptions(),
      fetchMetrics(dashboardScope, dashboardSpaceIds),
      fetchBudgetConfig(),
      fetchPeriodStatus(dashboardScope, dashboardSpaceIds),
      fetchAlerts(),
      fetchTrips(),
      fetchGroups(),
    ])
      .then(([sum, tr, cat, bud, inc, incSum, rec, pend, led, opts, met, bcfg, pstat, alrt, trps, grps]) => {
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
        setDisplayCurrency(opts.base_currency)
        setMetrics(met)
        setBudgetConfigState(bcfg)
        setPeriodStatus(pstat)
        setAlerts(alrt)
        setTrips(trps)
        setGroups(grps)
        setError(null)
      })
      .catch((err) => setError(err.message))
  }

  // Re-fetch just the dashboard-relevant data scoped to "all", "personal", or one space.
  function handleSetDashboardScope(scope) {
    setDashboardScopeState(scope)
    setDashboardSpaceIdsState([])
    return Promise.all([
      fetchSummary(scope),
      fetchTrends(scope),
      fetchCategories(scope),
      fetchBudgetStatus(scope),
      fetchMetrics(scope),
      fetchPeriodStatus(scope),
    ])
      .then(([sum, tr, cat, bud, met, pstat]) => {
        setSummary(sum)
        setTrends(tr)
        setCategories(cat)
        setBudgets(bud)
        setMetrics(met)
        setPeriodStatus(pstat)
        setError(null)
      })
      .catch((err) => setError(err.message))
  }

  // Re-fetch scoped to a combined view across several chosen Expense Spaces.
  function handleSetDashboardSpaceIds(spaceIds) {
    setDashboardSpaceIdsState(spaceIds)
    return Promise.all([
      fetchSummary(null, spaceIds),
      fetchTrends(null, spaceIds),
      fetchCategories(null, spaceIds),
      fetchBudgetStatus(null, spaceIds),
      fetchMetrics(null, spaceIds),
      fetchPeriodStatus(null, spaceIds),
    ])
      .then(([sum, tr, cat, bud, met, pstat]) => {
        setSummary(sum)
        setTrends(tr)
        setCategories(cat)
        setBudgets(bud)
        setMetrics(met)
        setPeriodStatus(pstat)
        setError(null)
      })
      .catch((err) => setError(err.message))
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

  return {
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

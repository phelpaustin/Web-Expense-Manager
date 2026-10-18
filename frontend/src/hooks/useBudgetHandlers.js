import { setBudget, deleteBudget, setBudgetConfig } from '../api/client.js'
import { PART } from './useAppData.js'

const BUDGET_PARTS = [PART.DASHBOARD, PART.BUDGET_CONFIG]

export function useBudgetHandlers(loadAll, setError) {
  async function handleSetBudget(category, amount, currency) {
    const value = parseFloat(amount)
    if (!value || value <= 0) return false
    try {
      await setBudget(category, value, currency)
      await loadAll(BUDGET_PARTS)
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }

  async function handleDeleteBudget(category) {
    try {
      await deleteBudget(category)
      await loadAll(BUDGET_PARTS)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSetBudgetConfig(period, rollover) {
    try {
      await setBudgetConfig(period, rollover)
      await loadAll(BUDGET_PARTS)
    } catch (err) {
      setError(err.message)
    }
  }

  return { handleSetBudget, handleDeleteBudget, handleSetBudgetConfig }
}

import { setBudget, deleteBudget, setBudgetConfig } from '../api/client.js'

export function useBudgetHandlers(loadAll, setError) {
  async function handleSetBudget(category, amount) {
    const value = parseFloat(amount)
    if (!value || value <= 0) return false
    try {
      await setBudget(category, value)
      await loadAll()
      return true
    } catch (err) {
      setError(err.message)
      return false
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

  async function handleSetBudgetConfig(period, rollover) {
    try {
      await setBudgetConfig(period, rollover)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return { handleSetBudget, handleDeleteBudget, handleSetBudgetConfig }
}

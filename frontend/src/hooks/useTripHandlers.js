import { createTrip, updateTrip, deleteTrip } from '../api/client.js'
import { EXPENSE_PARTS } from './useAppData.js'

export function useTripHandlers(loadAll, setError) {
  // Resolves to false when the trip could not be created, so the form can keep what was typed.
  async function handleAddTrip(trip) {
    try {
      await createTrip(trip)
      await loadAll(EXPENSE_PARTS)
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }

  async function handleUpdateTrip(id, trip) {
    try {
      await updateTrip(id, trip)
      await loadAll(EXPENSE_PARTS)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteTrip(id) {
    try {
      await deleteTrip(id)
      await loadAll(EXPENSE_PARTS)
    } catch (err) {
      setError(err.message)
    }
  }

  return { handleAddTrip, handleUpdateTrip, handleDeleteTrip }
}

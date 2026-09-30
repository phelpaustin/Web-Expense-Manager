import { createTrip, updateTrip, deleteTrip } from '../api/client.js'

export function useTripHandlers(loadAll, setError) {
  async function handleAddTrip(trip) {
    try {
      await createTrip(trip)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleUpdateTrip(id, trip) {
    try {
      await updateTrip(id, trip)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteTrip(id) {
    try {
      await deleteTrip(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return { handleAddTrip, handleUpdateTrip, handleDeleteTrip }
}

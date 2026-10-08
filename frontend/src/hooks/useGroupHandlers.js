import { createGroup, deleteGroup, leaveGroup } from '../api/client.js'

export function useGroupHandlers(loadAll, setError) {
  async function handleCreateGroup(name, spaceType, currency) {
    try {
      await createGroup(name, spaceType, currency)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteGroup(id) {
    try {
      await deleteGroup(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleLeaveGroup(id) {
    try {
      await leaveGroup(id)
      await loadAll()
    } catch (err) {
      setError(err.message)
    }
  }

  return { handleCreateGroup, handleDeleteGroup, handleLeaveGroup }
}

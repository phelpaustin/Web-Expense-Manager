import { useEffect, useState } from 'react'
import { fetchMe, getToken, logout, deleteAccount } from '../api/client.js'

// Session/auth lifecycle: who's logged in, and the mount-time token check.
// loadAll/resetData come from useAppData so a fresh login or logout can drive them.
export function useAuth(loadAll, resetData, setError) {
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [loading, setLoading] = useState(true)

  // On mount, if a token exists, verify it and load the user's data.
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true)
      setLoading(false)
      return
    }
    fetchMe()
      .then((me) => {
        setUser(me)
        return loadAll()
      })
      .catch(() => {
        logout()
      })
      .finally(() => {
        setAuthChecked(true)
        setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleAuthed() {
    setLoading(true)
    fetchMe()
      .then((me) => {
        setUser(me)
        return loadAll()
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  function handleLogout() {
    logout()
    setUser(null)
    resetData()
  }

  async function handleDeleteAccount(password) {
    await deleteAccount(password)
    handleLogout()
  }

  return { user, authChecked, loading, handleAuthed, handleLogout, handleDeleteAccount }
}

import { useEffect, useRef, useState } from 'react'
import { fetchMe, getToken, logout, deleteAccount, onSessionExpired } from '../api/client.js'

const SESSION_EXPIRED_NOTICE = 'Your session has expired. Please sign in again.'

// Session/auth lifecycle: who's logged in, and the mount-time token check.
// loadAll/resetData come from useAppData so a fresh login or logout can drive them.
export function useAuth(loadAll, resetData, setError) {
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [loading, setLoading] = useState(true)
  // Shown on the sign-in screen after the server ended the session.
  const [sessionNotice, setSessionNotice] = useState(null)
  // Set when a saved session could not be checked because the server was unreachable
  // or failing. The token is kept, so a retry can restore the session.
  const [authError, setAuthError] = useState(null)

  // Always call the latest versions from inside effects and subscriptions.
  const latest = useRef({ loadAll, resetData })
  latest.current = { loadAll, resetData }

  // The server rejected our token while the app was in use (it expired, or another
  // device logged out): return to the sign-in screen instead of leaving a dead UI.
  useEffect(
    () =>
      onSessionExpired(() => {
        setUser(null)
        latest.current.resetData()
        setSessionNotice(SESSION_EXPIRED_NOTICE)
      }),
    [],
  )

  // Verify the saved token and load the user's data. Only a 401 means the session is
  // over (request() has then already cleared the token). Anything else, such as the
  // backend waking from a cold start or a brief network drop, must not log the user
  // out: that would discard a valid token and, via the server's logout, end the
  // session on every device.
  function restoreSession() {
    setAuthError(null)
    setLoading(true)
    return fetchMe()
      .then((me) => {
        setUser(me)
        return latest.current.loadAll()
      })
      .catch((err) => {
        if (err.status !== 401) {
          setAuthError('Can’t reach the server right now. Your session is kept; try again in a moment.')
        }
      })
      .finally(() => {
        setAuthChecked(true)
        setLoading(false)
      })
  }

  // On mount, if a token exists, verify it and load the user's data.
  useEffect(() => {
    if (!getToken()) {
      setAuthChecked(true)
      setLoading(false)
      return
    }
    restoreSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleAuthed() {
    setSessionNotice(null)
    setAuthError(null)
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
    void logout()
    setUser(null)
    setSessionNotice(null)
    resetData()
  }

  async function handleDeleteAccount(confirmation) {
    await deleteAccount(confirmation)
    handleLogout()
  }

  return {
    user,
    authChecked,
    loading,
    sessionNotice,
    authError,
    retryAuth: restoreSession,
    handleAuthed,
    handleLogout,
    handleDeleteAccount,
  }
}

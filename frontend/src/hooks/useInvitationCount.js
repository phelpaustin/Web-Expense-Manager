import { useEffect, useState } from 'react'
import { fetchInvitations } from '../api/client.js'

// How many invitations to shared spaces are waiting, for the badge on Settings. Best effort: a failed
// lookup just shows no badge. The Spaces tab reports changes (accepting, declining) through setCount.
export function useInvitationCount(signedIn) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!signedIn) {
      setCount(0)
      return undefined
    }
    let live = true
    fetchInvitations()
      .then((list) => live && setCount(Array.isArray(list) ? list.length : 0))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [signedIn])
  return [count, setCount]
}

import { useEffect, useState } from 'react'
import { fetchInvitations, acceptInvitation, declineInvitation } from '../api/client.js'

// Invitations to shared spaces. Being invited never adds anyone: the invitee accepts here.
export default function Invitations({ onAccepted, onError, onCount }) {
  const [invites, setInvites] = useState([])
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    let live = true
    fetchInvitations()
      .then((list) => {
        if (!live) return
        const next = Array.isArray(list) ? list : []
        setInvites(next)
        onCount?.(next.length)
      })
      .catch((err) => live && onError(err.message))
    return () => {
      live = false
    }
  }, [])

  async function answer(invite, accept) {
    setBusyId(invite.id)
    try {
      if (accept) await acceptInvitation(invite.id)
      else await declineInvitation(invite.id)
      setInvites((prev) => {
        const next = prev.filter((i) => i.id !== invite.id)
        onCount?.(next.length)
        return next
      })
      if (accept) await onAccepted()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  if (invites.length === 0) return null
  return (
    <section className="card" aria-label="Invitations">
      <h2>Invitations</h2>
      {invites.map((i) => (
        <div key={i.id} className="invite-row" style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '0.5rem' }}>
          <span style={{ flex: 1 }}>
            <strong>{i.invited_by}</strong> invited you to <strong>{i.group_name}</strong> as {i.role}
          </span>
          <button type="button" disabled={busyId === i.id} onClick={() => answer(i, true)}>
            Accept
          </button>
          <button type="button" className="link-btn" disabled={busyId === i.id} onClick={() => answer(i, false)}>
            Decline
          </button>
        </div>
      ))}
    </section>
  )
}

import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { unsubscribeDigest } from '../api/client.js'

// Opened from the link in a budget alert email. Works without signing in; the link's
// signed token identifies the account. The click on the button (not just opening the
// page) is what unsubscribes, so mail scanners that pre-open links do not do it.
export default function UnsubscribePage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') || ''
  const [state, setState] = useState('ask') // ask | busy | done
  const [error, setError] = useState(null)

  async function handleUnsubscribe() {
    setError(null)
    setState('busy')
    try {
      await unsubscribeDigest(token)
      setState('done')
    } catch (err) {
      setError(err.message)
      setState('ask')
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>💳 Expense Dashboard</h1>
        <p className="subtitle">Budget alert emails</p>
        {state === 'done' ? (
          <div className="ok-note">
            You are unsubscribed and will not get budget alert emails any more. You can turn them back on in Settings.
          </div>
        ) : (
          <>
            {!token && <div className="auth-error">This unsubscribe link is incomplete. Use the link from your email.</div>}
            {error && <div className="auth-error">{error}</div>}
            <p>Stop sending budget alert emails to your address?</p>
            <button type="button" onClick={handleUnsubscribe} disabled={!token || state === 'busy'}>
              {state === 'busy' ? 'Unsubscribing…' : 'Unsubscribe'}
            </button>
          </>
        )}
        <p className="auth-toggle">
          <button type="button" className="link" onClick={() => navigate('/')}>
            Go to the app
          </button>
        </p>
      </div>
    </div>
  )
}

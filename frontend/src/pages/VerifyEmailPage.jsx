import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { verifyEmail } from '../api/client.js'

export default function VerifyEmailPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') || ''
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleVerify(event) {
    event.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await verifyEmail(token, name, password)
      setDone(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>💳 Expense Dashboard</h1>
        <p className="subtitle">Verify your email address</p>

        {done ? (
          <>
            <div className="ok-note">Email verified. You can now sign in.</div>
            <p className="auth-toggle">
              <button type="button" className="link" onClick={() => navigate('/')}>
                Continue to sign in
              </button>
            </p>
          </>
        ) : (
          <>
            {!token && <div className="auth-error">Missing verification token. Use the link from your email.</div>}
            {error && <div className="auth-error">{error}</div>}
            <form className="auth-form" onSubmit={handleVerify}>
              <input
                type="text"
                placeholder="Full name (optional)"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <input
                type="password"
                placeholder="Choose a password (min 12 characters)"
                required
                minLength={12}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <input
                type="password"
                placeholder="Confirm password"
                required
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
              <button type="submit" disabled={busy || !token}>
                {busy ? 'Verifying…' : 'Verify email and create account'}
              </button>
            </form>
            <p className="auth-toggle">
              <button type="button" className="link" onClick={() => navigate('/')}>
                Back to sign in
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  )
}

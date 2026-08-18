import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { resetPassword } from '../api/client.js'

export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') || ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      await resetPassword(token, password)
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
        <p className="subtitle">Choose a new password</p>

        {!token && <div className="auth-error">Missing reset token. Use the link from your email.</div>}

        {done ? (
          <>
            <div className="ok-note">Password updated. You can now sign in.</div>
            <p className="auth-toggle">
              <button type="button" className="link" onClick={() => navigate('/')}>
                Go to sign in
              </button>
            </p>
          </>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <input
              type="password"
              placeholder="New password (min 6 characters)"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <input
              type="password"
              placeholder="Confirm new password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            {error && <div className="auth-error">{error}</div>}
            <button type="submit" disabled={busy || !token}>
              {busy ? 'Saving…' : 'Reset password'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

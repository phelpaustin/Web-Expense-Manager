import { useState } from 'react'
import { login, register, forgotPassword } from './api/client.js'

export default function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState('login') // 'login' | 'register' | 'forgot'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      if (mode === 'login') {
        await login(email, password)
        onAuthed()
      } else if (mode === 'register') {
        await register(email, password)
        onAuthed()
      } else {
        const res = await forgotPassword(email)
        setNotice(res.message || 'If that email is registered, a reset link has been sent.')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const title =
    mode === 'login' ? 'Sign in to continue' : mode === 'register' ? 'Create an account' : 'Reset your password'

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>💳 Expense Dashboard</h1>
        <p className="subtitle">{title}</p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {mode !== 'forgot' && (
            <input
              type="password"
              placeholder="Password (min 6 characters)"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          {error && <div className="auth-error">{error}</div>}
          {notice && <div className="ok-note">{notice}</div>}
          <button type="submit" disabled={busy}>
            {busy
              ? 'Please wait…'
              : mode === 'login'
                ? 'Sign in'
                : mode === 'register'
                  ? 'Sign up'
                  : 'Send reset link'}
          </button>
        </form>

        {mode === 'login' && (
          <p className="auth-toggle">
            <button
              type="button"
              className="link"
              onClick={() => {
                setError(null)
                setNotice(null)
                setMode('forgot')
              }}
            >
              Forgot password?
            </button>
          </p>
        )}

        <p className="auth-toggle">
          {mode === 'register' ? 'Already have an account? ' : "Don't have an account? "}
          <button
            type="button"
            className="link"
            onClick={() => {
              setError(null)
              setNotice(null)
              setMode(mode === 'register' ? 'login' : mode === 'forgot' ? 'login' : 'register')
            }}
          >
            {mode === 'register' ? 'Sign in' : mode === 'forgot' ? 'Back to sign in' : 'Sign up'}
          </button>
        </p>

        {import.meta.env.DEV && mode === 'login' && (
          <p className="auth-demo">Demo account: demo@example.com / demo1234</p>
        )}
      </div>
    </div>
  )
}

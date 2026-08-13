import { useState } from 'react'
import { login, register } from './api/client.js'

export default function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        await register(email, password)
      }
      onAuthed()
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
        <p className="subtitle">{mode === 'login' ? 'Sign in to continue' : 'Create an account'}</p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            type="password"
            placeholder="Password (min 6 characters)"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Sign up'}
          </button>
        </form>

        <p className="auth-toggle">
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <button
            type="button"
            className="link"
            onClick={() => {
              setError(null)
              setMode(mode === 'login' ? 'register' : 'login')
            }}
          >
            {mode === 'login' ? 'Sign up' : 'Sign in'}
          </button>
        </p>

        {import.meta.env.DEV && (
          <p className="auth-demo">Demo account: demo@example.com / demo1234</p>
        )}
      </div>
    </div>
  )
}

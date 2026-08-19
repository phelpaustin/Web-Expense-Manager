import { useState, useEffect, useRef } from 'react'
import { login, register, forgotPassword, googleLogin } from './api/client.js'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

export default function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState('login') // 'login' | 'register' | 'forgot'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [busy, setBusy] = useState(false)
  const googleBtnRef = useRef(null)

  // Render the Google Sign-In button (only if a client ID is configured).
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || mode === 'forgot') return

    function init() {
      if (!window.google || !googleBtnRef.current) return
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (resp) => {
          try {
            await googleLogin(resp.credential)
            onAuthed()
          } catch (err) {
            setError(err.message)
          }
        },
      })
      googleBtnRef.current.innerHTML = ''
      window.google.accounts.id.renderButton(googleBtnRef.current, {
        theme: 'outline',
        size: 'large',
        width: 300,
      })
    }

    const id = 'google-gsi'
    if (window.google) {
      init()
    } else if (!document.getElementById(id)) {
      const s = document.createElement('script')
      s.src = 'https://accounts.google.com/gsi/client'
      s.async = true
      s.defer = true
      s.id = id
      s.onload = init
      document.body.appendChild(s)
    } else {
      document.getElementById(id).addEventListener('load', init)
    }
  }, [mode, onAuthed])

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
        await register(email, password, name)
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
          {mode === 'register' && (
            <input
              type="text"
              placeholder="Full name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          )}
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

        {GOOGLE_CLIENT_ID && mode !== 'forgot' && (
          <>
            <div className="auth-divider">
              <span>or</span>
            </div>
            <div className="google-btn" ref={googleBtnRef}></div>
          </>
        )}

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

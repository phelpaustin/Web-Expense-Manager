import { useState, useEffect, useRef } from 'react'
import { login, register, forgotPassword, googleLogin, resendVerification } from './api/client.js'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

export default function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState('login') // 'login' | 'register' | 'forgot'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [verificationEmail, setVerificationEmail] = useState('')
  const [resendBusy, setResendBusy] = useState(false)
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
        const res = await register(email)
        setVerificationEmail(email)
        setPassword('')
        setNotice(res.message || 'Check your email for a verification link before signing in.')
      } else {
        const res = await forgotPassword(email)
        setNotice(res.message || 'If that email is registered, a reset link has been sent.')
      }
    } catch (err) {
      setError(err.message)
      if (mode === 'login' && err.message.toLowerCase().includes('verify your email')) {
        setVerificationEmail(email)
      }
      if (mode === 'register' && err.message.toLowerCase().includes('email already registered')) {
        setVerificationEmail(email)
      }
    } finally {
      setBusy(false)
    }
  }

  async function handleResendVerification() {
    if (!verificationEmail) return
    setError(null)
    setResendBusy(true)
    try {
      const res = await resendVerification(verificationEmail)
      setNotice(res.message || 'If that account needs verification, a new link has been sent.')
    } catch (err) {
      setError(err.message)
    } finally {
      setResendBusy(false)
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
          {mode === 'login' && (
            <input
              type="password"
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
          {mode === 'register' && (
            <p className="subtitle">We’ll email you a link. You’ll choose your name and password there.</p>
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

        {verificationEmail && mode !== 'forgot' && (
          <p className="auth-toggle">
            <button type="button" className="link" onClick={handleResendVerification} disabled={resendBusy}>
              {resendBusy ? 'Sending…' : 'Resend verification email'}
            </button>
          </p>
        )}

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

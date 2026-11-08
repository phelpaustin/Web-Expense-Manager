import { useState } from 'react'

// A password field with a Show/Hide button. Hidden by default, and hidden again whenever the page is
// left, since the state lives only in this component.
export default function PasswordInput(props) {
  const [shown, setShown] = useState(false)
  return (
    <span className="password-field">
      <input {...props} type={shown ? 'text' : 'password'} />
      <button
        type="button"
        className="password-toggle"
        aria-label={shown ? 'Hide password' : 'Show password'}
        aria-pressed={shown}
        onClick={() => setShown((v) => !v)}
      >
        {shown ? 'Hide' : 'Show'}
      </button>
    </span>
  )
}

import { useEffect, useRef } from 'react'

export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID

// Google's own button, used to prove who you are again before a destructive action
// (accounts that signed up with Google have no password to type). Renders nothing when
// Google sign-in is not configured. onCredential receives the Google ID token.
export default function GoogleConfirmButton({ onCredential, disabled = false }) {
  const ref = useRef(null)
  const latest = useRef(onCredential)
  latest.current = onCredential

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return undefined

    function init() {
      if (!window.google || !ref.current) return
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (resp) => latest.current && latest.current(resp.credential),
      })
      ref.current.innerHTML = ''
      window.google.accounts.id.renderButton(ref.current, { theme: 'outline', size: 'large', width: 300 })
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
    return undefined
  }, [])

  if (!GOOGLE_CLIENT_ID) return null
  return <div className="google-btn" ref={ref} style={disabled ? { opacity: 0.5, pointerEvents: 'none' } : undefined} />
}

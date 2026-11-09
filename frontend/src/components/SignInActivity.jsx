import { useEffect, useRef, useState } from 'react'
import { fetchSignIns } from '../api/client.js'

const METHODS = { password: 'Password', google: 'Google' }

function when(iso) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

// Settings → Account: who signed in to this account and when, including failed password attempts.
export default function SignInActivity({ onError }) {
  const [data, setData] = useState(null)
  const report = useRef(onError)
  report.current = onError

  // Once per visit to the tab, whatever the parent re-renders do.
  useEffect(() => {
    let live = true
    fetchSignIns()
      .then((d) => live && setData(d))
      .catch((err) => live && report.current?.(err.message))
    return () => {
      live = false
    }
  }, [])

  if (!data) return null
  const failures = data.failed_since_last_success

  return (
    <section className="panel">
      <h2>Sign-in activity</h2>
      <p className="muted-note">
        The last sign-ins and failed password attempts on this account, kept for {data.keep_days} days. If you
        see one you don’t recognise, change your password: that signs out every other device.
      </p>
      {failures > 0 && (
        <div className="auth-error" role="alert">
          {failures} failed {failures === 1 ? 'attempt' : 'attempts'} since your last successful sign-in.
        </div>
      )}
      {data.events.length === 0 ? (
        <p className="muted-note">Nothing recorded yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="signin-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Result</th>
                <th>How</th>
                <th>Device</th>
                <th>IP address</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e, i) => (
                <tr key={`${e.at}-${i}`} className={e.success ? '' : 'signin-failed'}>
                  <td>{when(e.at)}</td>
                  <td>{e.success ? 'Signed in' : 'Wrong password'}</td>
                  <td>{METHODS[e.method] || e.method}</td>
                  <td>{e.device || '—'}</td>
                  <td>{e.ip || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

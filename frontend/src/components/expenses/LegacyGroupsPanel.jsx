import { useCallback, useEffect, useState } from 'react'
import { money } from '../../format.js'
import { fetchLegacyGroups, resolveLegacyGroups } from '../../api/client.js'

// Purchases an older version put together by date and shop without being asked. The user decides
// for each one: keep it as an itemised bill (a real container) or split it into one purchase per
// expense. Shows nothing when there are none, which is the normal state once reviewed.
export default function LegacyGroupsPanel({ onChanged, onError }) {
  const [groups, setGroups] = useState([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setGroups(await fetchLegacyGroups())
    } catch (err) {
      onError?.(err.message)
    }
  }, [onError])

  useEffect(() => {
    load()
  }, [load])

  async function resolve(action, ids) {
    setBusy(true)
    try {
      await resolveLegacyGroups(action, ids)
      await load()
      await onChanged?.()
    } catch (err) {
      onError?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (groups.length === 0) return null
  const allIds = groups.map((g) => g.id)

  return (
    <div className="panel legacy-groups" role="region" aria-label="Purchases grouped automatically">
      <p style={{ margin: 0 }}>
        <strong>{groups.length}</strong> {groups.length === 1 ? 'purchase was' : 'purchases were'} put together
        automatically by date and shop by an older version.{' '}
        <button type="button" className="mini-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? 'Hide' : 'Review'}
        </button>
      </p>
      {open && (
        <>
          <p className="subtitle" style={{ margin: '0.5rem 0' }}>
            <b>Keep as one bill</b> if these items really were on one receipt. <b>Split</b> if they were
            separate purchases: each expense then becomes its own purchase.
          </p>
          <div className="legacy-actions">
            <button type="button" disabled={busy} onClick={() => resolve('keep', allIds)}>
              Keep all as bills
            </button>
            <button type="button" disabled={busy} onClick={() => resolve('split', allIds)}>
              Split all
            </button>
          </div>
          {groups.map((g) => (
            <div key={g.id} className="legacy-group">
              <div className="legacy-head">
                <span>
                  <strong>{g.shop}</strong> · {g.date} · {g.items.length} items ·{' '}
                  {money(g.amount, g.currency)}
                </span>
                <span className="legacy-actions">
                  <button type="button" className="mini-btn" disabled={busy} onClick={() => resolve('keep', [g.id])}>
                    Keep as one bill
                  </button>
                  <button type="button" className="mini-btn" disabled={busy} onClick={() => resolve('split', [g.id])}>
                    Split
                  </button>
                </span>
              </div>
              <ul className="legacy-items">
                {g.items.map((i) => (
                  <li key={i.id}>
                    {i.description || i.category} <span className="subtitle">{money(i.amount, g.currency)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

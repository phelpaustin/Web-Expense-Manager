import { useState } from 'react'
import { fetchAliases, fetchAliasSuggestions, mergeNames, deleteAlias } from '../api/client.js'

const KINDS = [
  { key: 'item', label: 'Items', plural: 'items' },
  { key: 'shop', label: 'Shops', plural: 'shops' },
]

const REASON = {
  size: 'Same name apart from a size or quantity',
  similar: 'Look like spelling variants',
}

const sameName = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase()

// One group of names that probably mean the same thing, with a choice of which to merge
// and what to call the result.
function SuggestionGroup({ group, busy, onMerge }) {
  const [picked, setPicked] = useState(() => new Set(group.names.map((n) => n.name)))
  const [canonical, setCanonical] = useState(group.suggested)

  const toMerge = [...picked].filter((name) => !sameName(name, canonical))

  function toggle(name) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  return (
    <div className="panel" style={{ marginBottom: '0.75rem' }}>
      <p className="subtitle" style={{ margin: '0 0 0.5rem' }}>
        {REASON[group.reason] || REASON.similar}
      </p>
      {group.names.map((n) => (
        <label key={n.name} style={{ display: 'block', margin: '0.2rem 0' }}>
          <input type="checkbox" checked={picked.has(n.name)} onChange={() => toggle(n.name)} /> {n.name}{' '}
          <span className="subtitle">
            ({n.count} {n.count === 1 ? 'purchase' : 'purchases'})
          </span>
        </label>
      ))}
      <label style={{ display: 'block', margin: '0.6rem 0' }}>
        Call it{' '}
        <input
          type="text"
          value={canonical}
          maxLength={200}
          onChange={(e) => setCanonical(e.target.value)}
          aria-label="Name to keep"
        />
      </label>
      <button type="button" disabled={busy || !canonical.trim() || toMerge.length === 0} onClick={() => onMerge(toMerge, canonical.trim())}>
        Merge {toMerge.length > 0 ? `${toMerge.length} into “${canonical.trim()}”` : ''}
      </button>
    </div>
  )
}

// Lets the user tell the price tracker which spellings are the same thing. Merges only
// change how the tracker groups names; the expenses themselves are never edited.
export default function TidyNames({ onChanged, onError }) {
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [kind, setKind] = useState('item')
  const [groups, setGroups] = useState({ item: [], shop: [] })
  const [aliases, setAliases] = useState({ items: [], shops: [] })
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      const [items, shops, saved] = await Promise.all([
        fetchAliasSuggestions('item'),
        fetchAliasSuggestions('shop'),
        fetchAliases(),
      ])
      setGroups({ item: items.groups, shop: shops.groups })
      setAliases(saved)
      setLoaded(true)
    } catch (err) {
      onError(err.message)
    }
  }

  function toggleOpen() {
    const next = !open
    setOpen(next)
    if (next && !loaded) load()
  }

  // Run a change, then refresh both this panel and the tracker's table.
  async function change(action) {
    setBusy(true)
    try {
      await action()
      await load()
      onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const current = KINDS.find((k) => k.key === kind)
  const shownGroups = groups[kind]
  const shownRules = kind === 'item' ? aliases.items : aliases.shops
  const suggestionCount = groups.item.length + groups.shop.length

  return (
    <div className="panel">
      <button type="button" aria-expanded={open} onClick={toggleOpen}>
        🧹 Tidy up names{loaded && suggestionCount > 0 ? ` (${suggestionCount} suggestions)` : ''}
      </button>
      {open && (
        <div style={{ marginTop: '1rem' }}>
          <p className="subtitle">
            Merge spellings of the same item or shop (like “Milk” and “Milk 1L”) so the tracker treats them as one. Your
            expenses are not changed, and you can undo any merge.
          </p>
          <div className="chips">
            {KINDS.map((k) => (
              <button key={k.key} type="button" aria-pressed={kind === k.key} onClick={() => setKind(k.key)}>
                {k.label} ({groups[k.key].length})
              </button>
            ))}
          </div>

          {!loaded ? (
            <p>Looking for duplicates…</p>
          ) : shownGroups.length === 0 ? (
            <p className="subtitle">No likely duplicate {current.plural} found.</p>
          ) : (
            shownGroups.map((g) => (
              <SuggestionGroup
                key={`${kind}:${g.names.map((n) => n.name).join('|')}`}
                group={g}
                busy={busy}
                onMerge={(names, canonical) => change(() => mergeNames(kind, names, canonical))}
              />
            ))
          )}

          {loaded && shownRules.length > 0 && (
            <>
              <h3>Your merged {current.plural}</h3>
              <div className="chips">
                {shownRules.map((r) => (
                  <span className="chip" key={r.id}>
                    {r.alias} → {r.canonical}
                    <button
                      type="button"
                      className="chip-x"
                      disabled={busy}
                      aria-label={`Undo merge of ${r.alias}`}
                      onClick={() => change(() => deleteAlias(r.id))}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

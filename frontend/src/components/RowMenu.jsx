import { useEffect, useRef, useState } from 'react'

// A "⋯" button opening a small menu of secondary actions. The list is positioned with
// `fixed` coordinates so it is never clipped by a scrolling table, and it closes on
// outside click, Escape, scroll or resize. Renders nothing when there are no items.
export default function RowMenu({ label, items }) {
  const visible = (items || []).filter(Boolean)
  const [pos, setPos] = useState(null) // null = closed
  const buttonRef = useRef(null)
  const listRef = useRef(null)
  const open = pos !== null

  useEffect(() => {
    if (!open) return undefined
    const close = () => setPos(null)
    const onKey = (e) => {
      if (e.key === 'Escape') {
        close()
        buttonRef.current?.focus()
      }
    }
    const onDown = (e) => {
      if (!listRef.current?.contains(e.target) && !buttonRef.current?.contains(e.target)) close()
    }
    listRef.current?.querySelector('button')?.focus()
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  if (visible.length === 0) return null

  const toggle = () => {
    if (open) return setPos(null)
    const r = buttonRef.current.getBoundingClientRect()
    const height = visible.length * 38 + 12
    const below = r.bottom + height + 8 < window.innerHeight
    setPos({
      right: Math.max(8, window.innerWidth - r.right),
      ...(below ? { top: r.bottom + 4 } : { bottom: window.innerHeight - r.top + 4 }),
    })
  }

  return (
    <span className="row-menu">
      <button
        type="button"
        ref={buttonRef}
        className="icon-btn row-menu-btn"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggle}
      >
        ⋯
      </button>
      {open && (
        <div className="row-menu-list" role="menu" ref={listRef} style={pos}>
          {visible.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className={item.danger ? 'danger' : ''}
              onClick={() => {
                setPos(null)
                item.onSelect()
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </span>
  )
}

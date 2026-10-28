import { useEffect, useId, useRef, useState } from 'react'
import './infoTip.css'

// An ⓘ button that shows a note when you hover it or click it (click again, press Esc or click
// elsewhere to close). Works with a keyboard and on touch screens, where there is no hover.
export default function InfoTip({ label = 'More info', children }) {
  const [pinned, setPinned] = useState(false) // opened by a click
  const [hover, setHover] = useState(false)
  const ref = useRef(null)
  const id = useId()
  const open = pinned || hover

  useEffect(() => {
    if (!open) return undefined
    const close = () => {
      setPinned(false)
      setHover(false)
    }
    const onKey = (e) => e.key === 'Escape' && close()
    const onOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) close()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onOutside)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onOutside)
    }
  }, [open])

  return (
    <span className="info-tip" ref={ref} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button
        type="button"
        className="info-tip-btn"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setPinned((p) => !p)}
      >
        i
      </button>
      {open && (
        <span role="tooltip" id={id} className="info-tip-pop">
          {children}
        </span>
      )}
    </span>
  )
}

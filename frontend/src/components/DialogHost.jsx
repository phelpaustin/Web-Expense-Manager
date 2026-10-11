import { useEffect, useRef, useState } from 'react'

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'

// Renders the dialog opened through useDialogs: a modal with a focus trap, Escape to cancel,
// click-outside to cancel, and focus returned to where it was when the dialog opened.
export default function DialogHost({ dialog, onClose }) {
  const panelRef = useRef(null)
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')

  // Reset the amount field for each new dialog.
  useEffect(() => {
    setAmount('')
    setError('')
  }, [dialog])

  useEffect(() => {
    if (!dialog) return undefined
    const previous = document.activeElement
    const panel = panelRef.current
    const target =
      panel.querySelector('[data-autofocus]') ||
      panel.querySelector('input') ||
      panel.querySelector('button.dialog-primary') ||
      panel.querySelector(FOCUSABLE)
    target?.focus()

    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose(dialog.cancelValue)
      } else if (e.key === 'Tab') {
        const items = [...panel.querySelectorAll(FOCUSABLE)]
        if (items.length === 0) return
        const first = items[0]
        const last = items[items.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('keydown', onKey, true)
      previous?.focus?.()
    }
  }, [dialog, onClose])

  if (!dialog) return null

  const submitAmount = (e) => {
    e.preventDefault()
    const n = parseFloat(amount)
    if (!Number.isFinite(n) || n <= 0) {
      setError('Enter an amount greater than zero')
      return
    }
    onClose(n)
  }

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose(dialog.cancelValue)
      }}
    >
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" ref={panelRef}>
        <h2 id="dialog-title">{dialog.title}</h2>
        {dialog.message && <p className="dialog-message">{dialog.message}</p>}
        {dialog.detail && <p className="dialog-detail">{dialog.detail}</p>}

        {dialog.kind === 'confirm' && (
          <div className="dialog-actions">
            <button type="button" className="ghost-btn" data-autofocus={dialog.danger ? '' : undefined} onClick={() => onClose(false)}>
              {dialog.cancelLabel || 'Cancel'}
            </button>
            <button type="button" className={dialog.danger ? 'danger-btn dialog-primary' : 'dialog-primary'} onClick={() => onClose(true)}>
              {dialog.confirmLabel || 'OK'}
            </button>
          </div>
        )}

        {dialog.kind === 'choose' && (
          <div className="dialog-actions dialog-choices">
            {dialog.choices.map((c) => (
              <button
                key={c.key}
                type="button"
                className={c.primary ? 'dialog-primary' : c.danger ? 'danger-btn' : 'ghost-btn'}
                onClick={() => onClose(c.key)}
              >
                {c.label}
              </button>
            ))}
            <button type="button" className="link-btn" onClick={() => onClose(null)}>
              Cancel
            </button>
          </div>
        )}

        {dialog.kind === 'amount' && (
          <form onSubmit={submitAmount}>
            <label className="dialog-field">
              <span>Amount{dialog.currency ? ` (${dialog.currency})` : ''}</span>
              <input
                type="number"
                step="0.01"
                min="0.01"
                inputMode="decimal"
                value={amount}
                onChange={(e) => {
                  setAmount(e.target.value)
                  setError('')
                }}
                aria-invalid={error ? 'true' : undefined}
              />
            </label>
            {error && (
              <p className="dialog-error" role="alert">
                {error}
              </p>
            )}
            <div className="dialog-actions">
              <button type="button" className="ghost-btn" onClick={() => onClose(null)}>
                Cancel
              </button>
              <button type="submit" className="dialog-primary">
                {dialog.confirmLabel || 'OK'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

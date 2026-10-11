import { useCallback, useRef, useState } from 'react'

// Promise-based in-app dialogs, so flows can `await` an answer instead of calling the browser's
// window.confirm / window.prompt. Render <DialogHost dialog={dialog} onClose={close} /> once.
//
//   confirm({ title, message, confirmLabel, danger })        -> true | false
//   choose({ title, message, detail, choices })              -> chosen key | null
//   promptAmount({ title, message, currency, confirmLabel }) -> positive number | null
export function useDialogs() {
  const [dialog, setDialog] = useState(null)
  const resolver = useRef(null)

  const close = useCallback((value) => {
    const current = resolver.current
    resolver.current = null
    setDialog(null)
    if (current) current.resolve(value)
  }, [])

  const open = useCallback((spec, cancelValue) => {
    // Only one dialog at a time: opening another cancels the one on screen, with the
    // cancel value of *that* dialog (false for a confirm, null for a choice or amount).
    if (resolver.current) resolver.current.resolve(resolver.current.cancelValue)
    return new Promise((resolve) => {
      resolver.current = { resolve, cancelValue }
      setDialog({ ...spec, cancelValue })
    })
  }, [])

  return {
    dialog,
    close,
    confirm: useCallback((spec) => open({ kind: 'confirm', ...spec }, false), [open]),
    choose: useCallback((spec) => open({ kind: 'choose', ...spec }, null), [open]),
    promptAmount: useCallback((spec) => open({ kind: 'amount', ...spec }, null), [open]),
  }
}

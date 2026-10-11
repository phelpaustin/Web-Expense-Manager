import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react'
import { useDialogs } from '../hooks/useDialogs.js'
import DialogHost from '../components/DialogHost.jsx'

// ── useDialogs: promise-based answers ──
describe('useDialogs', () => {
  it('confirm resolves true or false', async () => {
    const { result } = renderHook(() => useDialogs())
    let p
    act(() => { p = result.current.confirm({ title: 'Sure?' }) })
    expect(result.current.dialog).toMatchObject({ kind: 'confirm', title: 'Sure?' })
    act(() => result.current.close(true))
    await expect(p).resolves.toBe(true)
    expect(result.current.dialog).toBeNull()
    act(() => { p = result.current.confirm({ title: 'Sure?' }) })
    act(() => result.current.close(false))
    await expect(p).resolves.toBe(false)
  })

  it('choose resolves the chosen key', async () => {
    const { result } = renderHook(() => useDialogs())
    let p
    act(() => { p = result.current.choose({ title: 'Pick', choices: [{ key: 'a', label: 'A' }] }) })
    act(() => result.current.close('a'))
    await expect(p).resolves.toBe('a')
  })

  it('promptAmount resolves a number', async () => {
    const { result } = renderHook(() => useDialogs())
    let p
    act(() => { p = result.current.promptAmount({ title: 'Amount', currency: 'SEK' }) })
    expect(result.current.dialog).toMatchObject({ kind: 'amount', currency: 'SEK' })
    act(() => result.current.close(12.5))
    await expect(p).resolves.toBe(12.5)
  })

  it('opening a second dialog cancels the first with its cancel value', async () => {
    const { result } = renderHook(() => useDialogs())
    let first, second
    act(() => { first = result.current.confirm({ title: 'One' }) })
    act(() => { second = result.current.choose({ title: 'Two', choices: [] }) })
    await expect(first).resolves.toBe(false) // a cancelled confirm is false
    expect(result.current.dialog.title).toBe('Two')
    act(() => result.current.close('x'))
    await expect(second).resolves.toBe('x')
  })

  it('closing when nothing is open is harmless', () => {
    const { result } = renderHook(() => useDialogs())
    expect(() => act(() => result.current.close(true))).not.toThrow()
  })

  it('cancelling uses a value of the right kind (false / null)', async () => {
    const { result } = renderHook(() => useDialogs())
    let p
    act(() => { p = result.current.promptAmount({ title: 'Amount' }) })
    expect(result.current.dialog.cancelValue).toBeNull()
    act(() => result.current.close(result.current.dialog.cancelValue))
    await expect(p).resolves.toBeNull()
  })
})

// ── DialogHost: what you see and how it behaves ──
const confirmSpec = { kind: 'confirm', title: 'Delete this bill?', message: 'H&M · 2026-07-31', confirmLabel: 'Delete bill', danger: true, cancelValue: false }

describe('DialogHost', () => {
  it('renders nothing when there is no dialog', () => {
    const { container } = render(<DialogHost dialog={null} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('is an accessible modal dialog labelled by its title', () => {
    render(<DialogHost dialog={confirmSpec} onClose={() => {}} />)
    const dialog = screen.getByRole('dialog', { name: 'Delete this bill?' })
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(screen.getByText('H&M · 2026-07-31')).toBeTruthy()
  })

  it('confirms or cancels with the buttons', () => {
    const onClose = vi.fn()
    render(<DialogHost dialog={confirmSpec} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete bill' }))
    expect(onClose).toHaveBeenLastCalledWith(true)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenLastCalledWith(false)
  })

  it('starts on Cancel for a destructive action, so a stray Enter cannot delete', () => {
    render(<DialogHost dialog={confirmSpec} onClose={() => {}} />)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel' }))
  })

  it('starts on the main button for an ordinary confirmation', () => {
    render(<DialogHost dialog={{ ...confirmSpec, danger: false, confirmLabel: 'OK' }} onClose={() => {}} />)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'OK' }))
  })

  it('Escape cancels with the dialog\'s cancel value', () => {
    const onClose = vi.fn()
    render(<DialogHost dialog={confirmSpec} onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledWith(false)
  })

  it('clicking the backdrop cancels, clicking inside does not', () => {
    const onClose = vi.fn()
    const { container } = render(<DialogHost dialog={confirmSpec} onClose={onClose} />)
    fireEvent.mouseDown(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.mouseDown(container.querySelector('.dialog-backdrop'))
    expect(onClose).toHaveBeenCalledWith(false)
  })

  it('keeps Tab focus inside the dialog (wraps both ways)', () => {
    render(<DialogHost dialog={confirmSpec} onClose={() => {}} />)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    const confirm = screen.getByRole('button', { name: 'Delete bill' })
    confirm.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(cancel) // last -> first
    cancel.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(confirm) // first -> last
  })

  it('returns focus to what had it before the dialog opened', () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const { unmount } = render(<DialogHost dialog={confirmSpec} onClose={() => {}} />)
    expect(document.activeElement).not.toBe(opener)
    unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('choose: one button per choice, plus Cancel', () => {
    const onClose = vi.fn()
    const spec = {
      kind: 'choose', title: 'This looks like a bill you already have', detail: '2026-07-21 · LIDL · SEK 35.91', cancelValue: null,
      choices: [{ key: 'attach', label: 'Attach receipt to this bill', primary: true }, { key: 'new', label: 'Create a separate bill' }],
    }
    render(<DialogHost dialog={spec} onClose={onClose} />)
    expect(screen.getByText('2026-07-21 · LIDL · SEK 35.91')).toBeTruthy()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Attach receipt to this bill' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create a separate bill' }))
    expect(onClose).toHaveBeenLastCalledWith('new')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenLastCalledWith(null)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenLastCalledWith(null)
  })

  describe('amount prompt', () => {
    const spec = { kind: 'amount', title: 'Record total', message: 'No amount yet.', currency: 'SEK', confirmLabel: 'Record total', cancelValue: null }

    it('focuses the field and labels it with the currency', () => {
      render(<DialogHost dialog={spec} onClose={() => {}} />)
      const input = screen.getByLabelText('Amount (SEK)')
      expect(document.activeElement).toBe(input)
    })

    it('returns the number you typed', () => {
      const onClose = vi.fn()
      render(<DialogHost dialog={spec} onClose={onClose} />)
      fireEvent.change(screen.getByLabelText('Amount (SEK)'), { target: { value: '42.5' } })
      fireEvent.submit(screen.getByLabelText('Amount (SEK)').closest('form'))
      expect(onClose).toHaveBeenCalledWith(42.5)
    })

    it.each(['', '0', '-5', 'abc'])('refuses %j and says why, without closing', (bad) => {
      const onClose = vi.fn()
      render(<DialogHost dialog={spec} onClose={onClose} />)
      fireEvent.change(screen.getByLabelText('Amount (SEK)'), { target: { value: bad } })
      fireEvent.submit(screen.getByLabelText('Amount (SEK)').closest('form'))
      expect(screen.getByRole('alert').textContent).toBe('Enter an amount greater than zero')
      expect(onClose).not.toHaveBeenCalled()
    })

    it('clears the error once you type again, and cancel returns null', () => {
      const onClose = vi.fn()
      render(<DialogHost dialog={spec} onClose={onClose} />)
      fireEvent.submit(screen.getByLabelText('Amount (SEK)').closest('form'))
      expect(screen.getByRole('alert')).toBeTruthy()
      fireEvent.change(screen.getByLabelText('Amount (SEK)'), { target: { value: '5' } })
      expect(screen.queryByRole('alert')).toBeNull()
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
      expect(onClose).toHaveBeenCalledWith(null)
    })

    it('starts empty for each new prompt', () => {
      const { rerender } = render(<DialogHost dialog={spec} onClose={() => {}} />)
      fireEvent.change(screen.getByLabelText('Amount (SEK)'), { target: { value: '99' } })
      rerender(<DialogHost dialog={{ ...spec }} onClose={() => {}} />)
      expect(screen.getByLabelText('Amount (SEK)').value).toBe('')
    })
  })
})

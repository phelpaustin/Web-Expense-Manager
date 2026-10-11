import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RowMenu from '../components/RowMenu.jsx'
import Switch from '../components/Switch.jsx'

describe('RowMenu', () => {
  const items = (spies = {}) => [
    { label: 'Rename', onSelect: spies.rename || vi.fn() },
    { label: 'Delete bill', danger: true, onSelect: spies.remove || vi.fn() },
  ]

  it('renders nothing when there is nothing to put in it', () => {
    const { container } = render(<RowMenu label="More" items={[false, null, undefined]} />)
    expect(container.firstChild).toBeNull()
    const { container: empty } = render(<RowMenu label="More" items={[]} />)
    expect(empty.firstChild).toBeNull()
  })

  it('opens on click, listing only the real items', () => {
    render(<RowMenu label="More actions" items={[false, ...items()]} />)
    const button = screen.getByRole('button', { name: 'More actions' })
    expect(button.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('menu')).toBeNull()
    fireEvent.click(button)
    expect(button.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['Rename', 'Delete bill'])
    expect(screen.getByRole('menuitem', { name: 'Delete bill' }).className).toContain('danger')
  })

  it('runs the chosen action and closes', () => {
    const remove = vi.fn()
    render(<RowMenu label="More actions" items={items({ remove })} />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete bill' }))
    expect(remove).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('toggles closed when the button is clicked again', () => {
    render(<RowMenu label="More actions" items={items()} />)
    const button = screen.getByRole('button', { name: 'More actions' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('closes on Escape and gives focus back to the button', () => {
    render(<RowMenu label="More actions" items={items()} />)
    const button = screen.getByRole('button', { name: 'More actions' })
    fireEvent.click(button)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
    expect(document.activeElement).toBe(button)
  })

  it('closes when you click elsewhere, but not when you click inside the menu', () => {
    render(
      <div>
        <RowMenu label="More actions" items={items()} />
        <p>elsewhere</p>
      </div>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.mouseDown(screen.getByRole('menu'))
    expect(screen.getByRole('menu')).toBeTruthy()
    fireEvent.mouseDown(screen.getByText('elsewhere'))
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('closes when the page scrolls (a fixed-position menu would otherwise float away)', () => {
    render(<RowMenu label="More actions" items={items()} />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.scroll(window)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  describe('placement', () => {
    const original = { height: window.innerHeight, width: window.innerWidth }
    afterEach(() => {
      window.innerHeight = original.height
      window.innerWidth = original.width
      vi.restoreAllMocks()
    })

    const openAt = (rect) => {
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ top: rect.top, bottom: rect.top + 24, right: 900, left: 870, width: 30, height: 24 })
      render(<RowMenu label="More actions" items={items()} />)
      fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
      return screen.getByRole('menu').style
    }

    it('opens below the button when there is room', () => {
      window.innerHeight = 800
      const style = openAt({ top: 100 })
      expect(style.top).toBe('128px')
      expect(style.bottom).toBe('')
    })

    it('opens upward near the bottom of the screen so it is not cut off', () => {
      window.innerHeight = 800
      const style = openAt({ top: 780 })
      expect(style.bottom).toBe('24px') // 800 - 780 + 4
      expect(style.top).toBe('')
    })
  })
})

describe('Switch', () => {
  it('is a labelled switch reflecting its state', () => {
    render(<Switch checked onChange={() => {}} label="Count new bills" description="On: counted." />)
    const toggle = screen.getByRole('switch', { name: /Count new bills/ })
    expect(toggle.checked).toBe(true)
    expect(screen.getByText('On: counted.')).toBeTruthy()
  })

  it('reports the new state as a boolean', () => {
    const onChange = vi.fn()
    const { rerender } = render(<Switch checked={false} onChange={onChange} label="Count" />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenLastCalledWith(true)
    rerender(<Switch checked onChange={onChange} label="Count" />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenLastCalledWith(false)
  })

  it('works without a description and clicking the label toggles it', () => {
    const onChange = vi.fn()
    render(<Switch checked={false} onChange={onChange} label="Just a label" />)
    fireEvent.click(screen.getByText('Just a label'))
    expect(onChange).toHaveBeenCalledWith(true)
    expect(document.querySelector('small')).toBeNull()
  })
})

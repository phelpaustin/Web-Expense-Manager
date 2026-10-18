import { describe, it, expect } from 'vitest'

// App.jsx loads these with React.lazy, which needs a default export that is a component.
const PAGES = [
  'Dashboard', 'Expenses', 'Income', 'Recurring', 'Bills', 'Settings', 'Trips',
  'PriceTracker', 'Shops', 'Groups', 'ResetPassword', 'VerifyEmail', 'Unsubscribe',
]

describe('lazy-loaded pages', () => {
  it.each(PAGES)('%sPage has a default-exported component', async (name) => {
    const mod = await import(`../pages/${name}Page.jsx`)
    expect(typeof mod.default).toBe('function')
  })
})

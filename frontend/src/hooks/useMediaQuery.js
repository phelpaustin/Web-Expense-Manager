import { useEffect, useState } from 'react'

const supported = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function'

// True while the screen matches a CSS media query, and follows it as the window changes.
// Where matchMedia does not exist (older browsers, tests) the answer is always false.
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => (supported() ? window.matchMedia(query).matches : false))
  useEffect(() => {
    if (!supported()) return undefined
    const mq = window.matchMedia(query)
    const update = () => setMatches(mq.matches)
    update()
    if (mq.addEventListener) {
      mq.addEventListener('change', update)
      return () => mq.removeEventListener('change', update)
    }
    mq.addListener(update) // very old Safari
    return () => mq.removeListener(update)
  }, [query])
  return matches
}

// Formats money using the user's chosen display currency.
// setDisplayCurrency() is called by App once options load.

let _currency = 'SEK'

export function setDisplayCurrency(code) {
  if (code) _currency = code
}

export function money(amount, currency) {
  const n = Number(amount || 0)
  const code = currency || _currency
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: code }).format(n)
  } catch {
    return `${n.toFixed(2)} ${code}`
  }
}

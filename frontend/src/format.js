// Formats money using the user's chosen display currency.
// setDisplayCurrency() is called by App once options load.

let _currency = 'SEK'

export function setDisplayCurrency(code) {
  if (code) _currency = code
}

export function money(amount) {
  const n = Number(amount || 0)
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: _currency }).format(n)
  } catch {
    return `${n.toFixed(2)} ${_currency}`
  }
}

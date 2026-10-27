// Editing a trip's details: build the form from the trip, and work out what actually changed.

export function tripFormFor(trip) {
  return {
    name: trip.name || '',
    destination: trip.destination || '',
    start_date: trip.start_date || '',
    end_date: trip.end_date || '',
    budget: trip.budget ? String(Number(trip.budget)) : '',
    currency: trip.currency || 'SEK',
  }
}

// { error } for input the server would refuse, otherwise { changes } holding only what differs
// ({} when nothing changed). Dates are ISO strings, so comparing them as text compares them as dates.
export function tripChanges(trip, form) {
  const name = form.name.trim()
  if (!name) return { error: 'Give the trip a name.' }
  if (form.start_date && form.end_date && form.end_date < form.start_date) {
    return { error: 'A trip can’t end before it starts.' }
  }
  let budget = null
  if (form.budget.trim() !== '') {
    budget = parseFloat(form.budget)
    if (!Number.isFinite(budget) || budget <= 0) return { error: 'The budget must be more than zero, or left empty.' }
  }
  const currency = form.currency.trim().toUpperCase()
  if (!currency) return { error: 'Enter a currency, for example SEK.' }

  const changes = {}
  if (name !== trip.name) changes.name = name
  if (form.destination.trim() !== (trip.destination || '')) changes.destination = form.destination.trim()
  const start = form.start_date || null
  if (start !== (trip.start_date || null)) changes.start_date = start
  const end = form.end_date || null
  if (end !== (trip.end_date || null)) changes.end_date = end
  const before = trip.budget ? Number(trip.budget) : null
  if (budget !== before) changes.budget = budget
  if (currency !== (trip.currency || 'SEK')) changes.currency = currency
  return { changes }
}

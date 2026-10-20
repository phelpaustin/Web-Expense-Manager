// Pure helpers for the statement import screen (kept out of the component so they can be tested).

export const AMOUNT_MODES = [
  { id: 'signed', label: 'One amount column' },
  { id: 'split', label: 'Separate money-out and money-in columns' },
  { id: 'direction', label: 'Amount column plus a Debit/Credit column' },
]

export const RULE_ACTIONS = [
  { id: '', label: 'No change' },
  { id: 'skip', label: 'Leave out' },
  { id: 'expense', label: 'Treat as expense' },
  { id: 'income', label: 'Treat as income' },
]

// Which way the money is described in this mapping.
export function amountMode(mapping) {
  if (mapping.debit || mapping.credit) return 'split'
  if (mapping.direction) return 'direction'
  return 'signed'
}

// Switching how the amount is described clears the columns that no longer apply, so the server
// never sees a mapping that mixes two ways of saying the same thing.
export function setAmountMode(mapping, mode) {
  const next = { ...mapping }
  if (mode === 'split') {
    next.amount = null
    next.direction = null
  } else if (mode === 'direction') {
    next.debit = null
    next.credit = null
  } else {
    next.debit = null
    next.credit = null
    next.direction = null
  }
  return next
}

export const emptyRule = () => ({ contains: '', action: '', category: '' })

// Half-filled rules are the person still typing; they are not sent (the server would reject them).
export function cleanRules(rules) {
  return (rules || [])
    .map((r) => ({
      contains: String(r.contains || '').trim(),
      action: r.action || null,
      category: String(r.category || '').trim() || null,
    }))
    .filter((r) => r.contains && (r.action || r.category))
}

// The mapping as the server should see it.
export function payloadMapping(mapping) {
  return { ...mapping, rules: cleanRules(mapping.rules) }
}

// A mapping coming back from the server or the assistant, with rules shaped for the editor.
export function editorMapping(mapping) {
  return {
    ...mapping,
    rules: (mapping.rules || []).map((r) => ({ contains: r.contains || '', action: r.action || '', category: r.category || '' })),
  }
}

export function commitLabel(summary) {
  if (!summary) return 'Import'
  const parts = []
  if (summary.new_expenses) parts.push(`${summary.new_expenses} expense${summary.new_expenses === 1 ? '' : 's'}`)
  if (summary.new_income) parts.push(`${summary.new_income} income`)
  return parts.length ? `Import ${parts.join(' and ')}` : 'Nothing new to import'
}

export function resultMessage(result) {
  const bits = [`Imported ${result.added_expenses} expense${result.added_expenses === 1 ? '' : 's'} and ${result.added_income} income.`]
  if (result.duplicates) bits.push(`${result.duplicates} already in your records.`)
  if (result.skipped) bits.push(`${result.skipped} left out.`)
  if (result.errors) bits.push(`${result.errors} could not be read.`)
  return bits.join(' ')
}

export const STATUS_LABEL = { new: 'New', duplicate: 'Already there', skipped: 'Left out', error: 'Problem' }

// What the per-row kind menu shows: the person's choice, otherwise what the file/rules decided.
export function rowChoice(row, overrides) {
  return overrides[row.line] || (row.status === 'skipped' || row.status === 'error' ? 'skip' : row.kind) || 'skip'
}

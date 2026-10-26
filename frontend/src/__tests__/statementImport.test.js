import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  amountMode,
  cleanRules,
  commitLabel,
  editorMapping,
  payloadMapping,
  resultMessage,
  rowChoice,
  setAmountMode,
} from '../statementImport.js'
import { analyzeStatement, assistStatement, commitStatement, previewStatement, saveImportProfile } from '../api/client.js'

describe('amount modes', () => {
  it('reads the mode from which columns are set', () => {
    expect(amountMode({ amount: 'A' })).toBe('signed')
    expect(amountMode({ debit: 'D', credit: 'C' })).toBe('split')
    expect(amountMode({ debit: 'D' })).toBe('split')
    expect(amountMode({ amount: 'A', direction: 'T' })).toBe('direction')
  })

  it('clears the columns of the other modes when switching', () => {
    const m = { amount: 'A', debit: 'D', credit: 'C', direction: 'T', date: 'Date' }
    expect(setAmountMode(m, 'split')).toEqual({ amount: null, debit: 'D', credit: 'C', direction: null, date: 'Date' })
    expect(setAmountMode(m, 'direction')).toEqual({ amount: 'A', debit: null, credit: null, direction: 'T', date: 'Date' })
    expect(setAmountMode(m, 'signed')).toEqual({ amount: 'A', debit: null, credit: null, direction: null, date: 'Date' })
  })
})

describe('rules', () => {
  it('drops half-typed rules and trims the rest', () => {
    expect(
      cleanRules([
        { contains: '  swish ', action: 'income', category: '' },
        { contains: '', action: 'skip', category: '' },
        { contains: 'x', action: '', category: '' },
        { contains: 'spotify', action: '', category: ' Fun ' },
      ]),
    ).toEqual([
      { contains: 'swish', action: 'income', category: null },
      { contains: 'spotify', action: null, category: 'Fun' },
    ])
  })

  it('round-trips between the server shape and the editor shape', () => {
    const server = { sign: 'negative_is_expense', rules: [{ contains: 'a', action: null, category: 'B' }] }
    const editor = editorMapping(server)
    expect(editor.rules).toEqual([{ contains: 'a', action: '', category: 'B' }])
    expect(payloadMapping(editor).rules).toEqual(server.rules)
    expect(editorMapping({}).rules).toEqual([])
  })
})

describe('wording', () => {
  it('labels the import button from the preview', () => {
    expect(commitLabel(null)).toBe('Import')
    expect(commitLabel({ new_expenses: 1, new_income: 0 })).toBe('Import 1 expense')
    expect(commitLabel({ new_expenses: 2, new_income: 3 })).toBe('Import 2 expenses and 3 income')
    expect(commitLabel({ new_expenses: 0, new_income: 0 })).toBe('Nothing new to import')
    expect(commitLabel({ new_expenses: 1, new_income: 0 }, 'bills')).toBe('Import 1 bill')
    expect(commitLabel({ new_expenses: 4, new_income: 2 }, 'bills')).toBe('Import 4 bills and 2 income')
  })

  it('summarises the result, mentioning only what happened', () => {
    expect(resultMessage({ added_expenses: 2, added_income: 1, duplicates: 0, skipped: 0, errors: 0 })).toBe('Imported 2 expenses and 1 income.')
    expect(resultMessage({ save_as: 'bills', added_bills: 3, recorded_bills: 3, added_income: 0, duplicates: 0, skipped: 0, errors: 0 })).toBe(
      'Imported 3 bills and 0 income. 3 counted as spending; itemise them whenever you like.',
    )
    expect(resultMessage({ save_as: 'bills', added_bills: 1, recorded_bills: 0, added_income: 0, duplicates: 0, skipped: 0, errors: 0 })).toBe(
      'Imported 1 bill and 0 income. They are waiting on the Bills page.',
    )
    expect(resultMessage({ added_expenses: 1, added_income: 0, duplicates: 4, skipped: 2, errors: 1 })).toBe(
      'Imported 1 expense and 0 income. 4 already in your records. 2 left out. 1 could not be read.',
    )
  })

  it('shows the persons choice, else what the file decided', () => {
    expect(rowChoice({ line: 3, kind: 'expense', status: 'new' }, {})).toBe('expense')
    expect(rowChoice({ line: 3, kind: 'expense', status: 'new' }, { 3: 'income' })).toBe('income')
    expect(rowChoice({ line: 3, kind: null, status: 'skipped' }, {})).toBe('skip')
    expect(rowChoice({ line: 3, kind: 'income', status: 'error' }, {})).toBe('skip')
  })
})

describe('import API calls', () => {
  let calls
  beforeEach(() => {
    calls = []
    localStorage.setItem('expense_token', 't')
    vi.stubGlobal('fetch', vi.fn(async (url, init) => {
      calls.push({ url, init })
      return { ok: true, status: 200, json: async () => ({}) }
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  const file = new File(['a,b'], 's.csv', { type: 'text/csv' })

  it('sends the file with the mapping as JSON text, without a Content-Type header', async () => {
    await previewStatement(file, { amount: 'A' }, { 3: 'skip' }, { 4: 'Food' })
    const { url, init } = calls[0]
    expect(url).toBe('/api/import/preview')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBeUndefined()
    expect(init.headers.Authorization).toBe('Bearer t')
    expect(init.body.get('file').name).toBe('s.csv')
    expect(JSON.parse(init.body.get('mapping'))).toEqual({ amount: 'A' })
    expect(JSON.parse(init.body.get('overrides'))).toEqual({ 3: 'skip' })
    expect(JSON.parse(init.body.get('categories'))).toEqual({ 4: 'Food' })
  })

  it('leaves out empty optional fields and passes a forced header row as text', async () => {
    await analyzeStatement(file)
    expect(calls[0].init.body.has('header_row')).toBe(false)
    await analyzeStatement(file, '3')
    expect(calls[1].init.body.get('header_row')).toBe('3')
    await commitStatement(file, { a: 1 })
    expect(calls[2].url).toBe('/api/import/commit')
    expect(calls[2].init.body.has('overrides')).toBe(true) // {} is a real (empty) value, not "missing"
  })

  it('sends the instruction as plain text', async () => {
    await assistStatement(file, { a: 1 }, 'skip transfers')
    expect(calls[0].url).toBe('/api/import/assist')
    expect(calls[0].init.body.get('instruction')).toBe('skip transfers')
  })

  it('saves a profile as JSON', async () => {
    await saveImportProfile('Bank', 'abc123ef', { amount: 'A' })
    expect(calls[0].init.method).toBe('PUT')
    expect(JSON.parse(calls[0].init.body)).toEqual({ name: 'Bank', signature: 'abc123ef', mapping: { amount: 'A' } })
  })
})

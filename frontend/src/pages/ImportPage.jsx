import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ExpenseFileImport from '../components/ExpenseFileImport.jsx'
import { money } from '../format.js'
import {
  analyzeStatement,
  assistStatement,
  commitStatement,
  previewStatement,
  saveImportProfile,
} from '../api/client.js'
import {
  AMOUNT_MODES,
  RULE_ACTIONS,
  SAVE_AS,
  STATUS_LABEL,
  amountMode,
  commitLabel,
  editorMapping,
  emptyRule,
  payloadMapping,
  resultMessage,
  rowChoice,
  setAmountMode,
} from '../statementImport.js'

const DATE_ORDERS = [
  { id: 'auto', label: 'Work it out from the file' },
  { id: 'ymd', label: 'Year first (2026-12-31)' },
  { id: 'dayfirst', label: 'Day first (31/12/2026)' },
  { id: 'monthfirst', label: 'Month first (12/31/2026)' },
]

const SIGNS = [
  { id: 'negative_is_expense', label: 'Negative = money out (expense), positive = money in (income)' },
  { id: 'positive_is_expense', label: 'Positive = money out (expense), negative = money in (income)' },
]

const FILTERS = ['all', 'new', 'duplicate', 'skipped', 'error']

function ColumnSelect({ label, columns, value, onChange, required }) {
  return (
    <label className="import-field">
      <span>
        {label}
        {required ? ' *' : ''}
      </span>
      <select aria-label={`${label} column`} value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">— none —</option>
        {columns.map((c, i) => (
          <option key={`${i}-${c}`} value={c}>
            {c}
          </option>
        ))}
      </select>
    </label>
  )
}

function StatementImport({ onImported, onError, countBillsAsSpending = true }) {
  const [file, setFile] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [mapping, setMapping] = useState(null)
  const [mode, setMode] = useState('signed')
  const [saveAs, setSaveAs] = useState('expenses')
  const [headerRow, setHeaderRow] = useState('')
  const [overrides, setOverrides] = useState({})
  const [categoryEdits, setCategoryEdits] = useState({})
  const [preview, setPreview] = useState(null)
  const [problems, setProblems] = useState([])
  const [filter, setFilter] = useState('all')
  const [busy, setBusy] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [assist, setAssist] = useState(null) // { busy, explanation, notes }
  const [profileName, setProfileName] = useState('')
  const [profileNote, setProfileNote] = useState('')
  const [result, setResult] = useState(null)
  const latest = useRef(0)

  function adopt(nextMapping) {
    const m = editorMapping(nextMapping)
    setMapping(m)
    setMode(amountMode(m))
  }

  function fail(err) {
    onError(err.message)
  }

  async function load(chosen, forcedHeaderRow) {
    setBusy(true)
    onError(null)
    try {
      const res = await analyzeStatement(chosen, forcedHeaderRow)
      setAnalysis(res)
      adopt(res.mapping)
      setHeaderRow(String(res.header_row))
      setOverrides({})
      setCategoryEdits({})
      setPreview(null)
      setProblems(res.problems || [])
      setAssist(null)
      setProfileName(res.profile ? res.profile.name : '')
      setProfileNote('')
    } catch (err) {
      setAnalysis(null)
      setMapping(null)
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  function onFile(e) {
    const chosen = e.target.files && e.target.files[0]
    setResult(null)
    if (!chosen) return
    setFile(chosen)
    load(chosen)
  }

  // Re-run the preview a moment after anything that affects it changes. Only the newest answer
  // may be shown, so a slow earlier one cannot overwrite a newer one.
  useEffect(() => {
    if (!file || !analysis || !mapping) return undefined
    const request = ++latest.current
    const timer = setTimeout(() => {
      previewStatement(file, payloadMapping(mapping), overrides, categoryEdits, saveAs)
        .then((res) => {
          if (request !== latest.current) return
          setProblems(res.problems || [])
          setPreview(res.problems && res.problems.length ? null : res)
          onError(null)
        })
        .catch((err) => {
          if (request === latest.current) fail(err)
        })
    }, 350)
    return () => clearTimeout(timer)
  }, [file, analysis, mapping, overrides, categoryEdits, saveAs])

  function change(patch) {
    setMapping((m) => ({ ...m, ...patch }))
  }

  function chooseMode(next) {
    setMode(next)
    setMapping((m) => setAmountMode(m, next))
  }

  function setRule(i, patch) {
    setMapping((m) => ({ ...m, rules: m.rules.map((r, n) => (n === i ? { ...r, ...patch } : r)) }))
  }

  async function askAssistant(e) {
    e.preventDefault()
    if (!instruction.trim()) return
    setAssist({ busy: true })
    onError(null)
    try {
      const res = await assistStatement(file, payloadMapping(mapping), instruction.trim())
      adopt(res.mapping)
      setAssist({ busy: false, explanation: res.explanation, notes: res.notes || [] })
      setInstruction('')
    } catch (err) {
      setAssist(null)
      fail(err)
    }
  }

  async function commit() {
    setBusy(true)
    onError(null)
    try {
      const res = await commitStatement(file, payloadMapping(mapping), overrides, categoryEdits, saveAs)
      setResult(res)
      setFile(null)
      setAnalysis(null)
      setMapping(null)
      setPreview(null)
      if (onImported) await onImported()
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  async function saveProfile(e) {
    e.preventDefault()
    if (!profileName.trim()) return
    try {
      const saved = await saveImportProfile(profileName.trim(), analysis.signature, payloadMapping(mapping))
      setProfileNote(`Saved as “${saved.name}”. Next time a file with these columns is opened, it is set up for you.`)
    } catch (err) {
      fail(err)
    }
  }

  const columns = analysis ? analysis.columns : []
  const rows = preview ? preview.rows : []
  const shown = rows.filter((r) => filter === 'all' || r.status === filter)
  const summary = preview ? preview.summary : null
  const canImport = !!summary && summary.new_expenses + summary.new_income > 0 && !busy

  return (
    <>
      <p className="subtitle">
        Open a CSV or Excel statement. The app guesses the columns, you can correct them or just tell the assistant what
        to do, and you see every row before anything is saved. Re-importing the same file adds nothing twice.
      </p>

      {result && (
        <p className="import-result" role="status">
          {resultMessage(result)}{' '}
          {result.save_as === 'bills' ? <Link to="/spending?view=receipts">See bills</Link> : <Link to="/spending?view=items">See expenses</Link>} · <Link to="/income">See income</Link>
        </p>
      )}

      <section className="panel">
        <label className="btn-upload">
          📄 Choose statement (.csv or .xlsx)
          <input type="file" aria-label="Statement file" accept=".csv,.xlsx" onChange={onFile} hidden />
        </label>
        {file && <span className="subtitle"> {file.name}</span>}
        {busy && !mapping && <p>Reading the file…</p>}
      </section>

      {analysis && mapping && (
        <>
          <section className="panel">
            <h3>Columns</h3>
            {analysis.profile && <p className="subtitle">Using your saved mapping “{analysis.profile.name}”.</p>}
            {(analysis.notes || []).filter((n) => !analysis.profile).map((n) => (
              <p key={n} className="subtitle">
                {n}
              </p>
            ))}

            <div className="import-grid">
              <label className="import-field">
                <span>Table starts on line</span>
                <span className="import-inline">
                  <input
                    type="number"
                    min="1"
                    aria-label="Header line"
                    value={headerRow === '' ? '' : Number(headerRow) + 1}
                    onChange={(e) => setHeaderRow(e.target.value === '' ? '' : String(Math.max(0, Number(e.target.value) - 1)))}
                  />
                  <button type="button" className="mini-btn" onClick={() => load(file, headerRow)} disabled={busy || headerRow === ''}>
                    Re-read
                  </button>
                </span>
              </label>
              <ColumnSelect label="Date" required columns={columns} value={mapping.date} onChange={(v) => change({ date: v })} />
              <ColumnSelect label="Description" columns={columns} value={mapping.description} onChange={(v) => change({ description: v })} />
              <ColumnSelect label="Shop" columns={columns} value={mapping.shop} onChange={(v) => change({ shop: v })} />
              <ColumnSelect label="Category" columns={columns} value={mapping.category} onChange={(v) => change({ category: v })} />
              <label className="import-field">
                <span>Date format</span>
                <select aria-label="Date format" value={mapping.date_order} onChange={(e) => change({ date_order: e.target.value })}>
                  {DATE_ORDERS.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <h3>Money in and out</h3>
            <div className="import-modes" role="radiogroup" aria-label="How the amount is shown">
              {AMOUNT_MODES.map((m) => (
                <label key={m.id}>
                  <input type="radio" name="amount-mode" checked={mode === m.id} onChange={() => chooseMode(m.id)} /> {m.label}
                </label>
              ))}
            </div>
            <div className="import-grid">
              {mode !== 'split' && (
                <ColumnSelect label="Amount" required columns={columns} value={mapping.amount} onChange={(v) => change({ amount: v })} />
              )}
              {mode === 'signed' && (
                <label className="import-field import-wide">
                  <span>Which sign is an expense?</span>
                  <select aria-label="Sign convention" value={mapping.sign} onChange={(e) => change({ sign: e.target.value })}>
                    {SIGNS.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {mode === 'split' && (
                <>
                  <ColumnSelect label="Money out (debit)" required columns={columns} value={mapping.debit} onChange={(v) => change({ debit: v })} />
                  <ColumnSelect label="Money in (credit)" required columns={columns} value={mapping.credit} onChange={(v) => change({ credit: v })} />
                </>
              )}
              {mode === 'direction' && (
                <ColumnSelect label="Debit/Credit" required columns={columns} value={mapping.direction} onChange={(v) => change({ direction: v })} />
              )}
              <label className="import-field">
                <span>Currency (all rows)</span>
                <input
                  aria-label="Currency"
                  maxLength={10}
                  placeholder="From the file, else your base currency"
                  value={mapping.currency || ''}
                  onChange={(e) => change({ currency: e.target.value.trim().toUpperCase() || null })}
                />
              </label>
              <ColumnSelect label="Currency column" columns={columns} value={mapping.currency_column} onChange={(v) => change({ currency_column: v })} />
            </div>
            <label>
              <input type="checkbox" checked={mapping.include_expenses} onChange={(e) => change({ include_expenses: e.target.checked })} /> Import expenses
            </label>{' '}
            <label>
              <input type="checkbox" checked={mapping.include_income} onChange={(e) => change({ include_income: e.target.checked })} /> Import income
            </label>

            <fieldset className="import-saveas">
              <legend>Save expenses as</legend>
              {SAVE_AS.map((o) => (
                <label key={o.value} className="import-mode">
                  <input type="radio" name="save-as" value={o.value} checked={saveAs === o.value} onChange={() => setSaveAs(o.value)} /> {o.label}
                  <span className="subtitle"> {o.help}</span>
                </label>
              ))}
              {saveAs === 'bills' && (
                <p className="subtitle">
                  {countBillsAsSpending
                    ? 'Bills count as spending straight away, as a single total each. Itemise them from Bills whenever you like.'
                    : 'Bills wait under Spending, By receipt, and do not count as spending until you record them (see Settings).'}
                </p>
              )}
            </fieldset>

            {problems.length > 0 && (
              <ul className="import-problems" role="alert">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
          </section>

          {analysis.ai_available && (
            <section className="panel">
              <h3>✨ Tell the assistant</h3>
              <p className="subtitle">
                For example: “Debits are negative, credits positive”, “skip transfers to my savings account”, “Swish from Anna
                is income” or “put Spotify under Entertainment”. Only the column names, about ten sample rows and your
                instruction are sent to the AI. The rest of the file stays on the server.
              </p>
              <form className="import-ai" onSubmit={askAssistant}>
                <textarea
                  aria-label="Instruction for the assistant"
                  rows={2}
                  maxLength={1000}
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="What should the import do?"
                />
                <button type="submit" disabled={!instruction.trim() || (assist && assist.busy)}>
                  {assist && assist.busy ? 'Thinking…' : 'Apply'}
                </button>
              </form>
              {assist && !assist.busy && (
                <div className="import-assist-note" role="status">
                  {assist.explanation && <p>{assist.explanation}</p>}
                  {(assist.notes || []).map((n) => (
                    <p key={n} className="subtitle">
                      {n}
                    </p>
                  ))}
                  <p className="subtitle">Check the preview below. Nothing is saved until you import.</p>
                </div>
              )}
            </section>
          )}

          <section className="panel">
            <h3>Rules</h3>
            <p className="subtitle">When a row’s description or shop contains the text, do this. The first matching rule wins.</p>
            {mapping.rules.map((r, i) => (
              <div className="import-rule" key={i}>
                <input
                  aria-label={`Rule ${i + 1} text`}
                  placeholder="Text to look for"
                  value={r.contains}
                  onChange={(e) => setRule(i, { contains: e.target.value })}
                />
                <select aria-label={`Rule ${i + 1} action`} value={r.action} onChange={(e) => setRule(i, { action: e.target.value })}>
                  {RULE_ACTIONS.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label}
                    </option>
                  ))}
                </select>
                <input
                  aria-label={`Rule ${i + 1} category`}
                  placeholder="Category (optional)"
                  value={r.category}
                  onChange={(e) => setRule(i, { category: e.target.value })}
                />
                <button
                  type="button"
                  className="delete-btn"
                  title="Remove rule"
                  onClick={() => setMapping((m) => ({ ...m, rules: m.rules.filter((_, n) => n !== i) }))}
                >
                  ✕
                </button>
              </div>
            ))}
            <button type="button" className="mini-btn" onClick={() => setMapping((m) => ({ ...m, rules: [...m.rules, emptyRule()] }))} disabled={mapping.rules.length >= 30}>
              + Add rule
            </button>
          </section>

          <section className="panel">
            <h3>Preview</h3>
            {!summary ? (
              <p className="subtitle">{problems.length ? 'Fix the columns above to see the preview.' : 'Loading preview…'}</p>
            ) : (
              <>
                <div className="cards">
                  <div className="card">
                    <div className="card-label">{saveAs === 'bills' ? 'New bills' : 'New expenses'}</div>
                    <div className="card-value">{summary.new_expenses}</div>
                    <div className="subtitle">{Object.entries(summary.expense_total).map(([c, v]) => money(v, c)).join(' · ') || '—'}</div>
                  </div>
                  <div className="card">
                    <div className="card-label">New income</div>
                    <div className="card-value">{summary.new_income}</div>
                    <div className="subtitle">{Object.entries(summary.income_total).map(([c, v]) => money(v, c)).join(' · ') || '—'}</div>
                  </div>
                  <div className="card">
                    <div className="card-label">Already there</div>
                    <div className="card-value">{summary.duplicates}</div>
                  </div>
                  <div className="card">
                    <div className="card-label">Left out / problems</div>
                    <div className="card-value">
                      {summary.skipped} / {summary.errors}
                    </div>
                  </div>
                </div>

                <div className="tabs" role="tablist" aria-label="Filter rows">
                  {FILTERS.map((f) => (
                    <button key={f} type="button" role="tab" aria-selected={filter === f} className={filter === f ? 'tab active' : 'tab'} onClick={() => setFilter(f)}>
                      {f === 'all' ? 'All' : STATUS_LABEL[f]}
                    </button>
                  ))}
                </div>

                <div className="table-wrap">
                  <table className="table import-table">
                    <thead>
                      <tr>
                        <th>Line</th>
                        <th>Date</th>
                        <th>Description</th>
                        <th className="right">Amount</th>
                        <th>Is</th>
                        <th>Category</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((r) => (
                        <tr key={r.line} className={`import-row import-${r.status}`}>
                          <td>{r.line}</td>
                          <td>{r.date}</td>
                          <td>{r.description}</td>
                          <td className="right">{r.amount ? money(r.amount, r.currency) : ''}</td>
                          <td>
                            <select
                              aria-label={`Line ${r.line} is`}
                              value={rowChoice(r, overrides)}
                              disabled={r.status === 'duplicate'}
                              onChange={(e) => setOverrides((o) => ({ ...o, [r.line]: e.target.value }))}
                            >
                              <option value="expense">Expense</option>
                              <option value="income">Income</option>
                              <option value="skip">Leave out</option>
                            </select>
                          </td>
                          <td>
                            {r.kind === 'expense' && r.status === 'new' ? (
                              <input
                                aria-label={`Line ${r.line} category`}
                                list="import-categories"
                                value={categoryEdits[r.line] ?? r.category}
                                onChange={(e) => setCategoryEdits((c) => ({ ...c, [r.line]: e.target.value }))}
                              />
                            ) : (
                              ''
                            )}
                          </td>
                          <td>
                            <span className={`import-badge import-badge-${r.status}`}>{STATUS_LABEL[r.status]}</span>
                            {(r.reason || r.rule) && <div className="subtitle">{r.reason || `Rule: ${r.rule}`}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <datalist id="import-categories">
                    {(preview.categories || []).map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </div>
                {preview.truncated && <p className="subtitle">Showing the first rows only. Everything in the file is imported, not just what is shown.</p>}

                <div className="import-actions">
                  <button type="button" onClick={commit} disabled={!canImport}>
                    {busy ? 'Importing…' : commitLabel(summary, saveAs)}
                  </button>
                </div>
              </>
            )}
          </section>

          <section className="panel">
            <h3>Remember this for next time</h3>
            <p className="subtitle">Save the columns and rules under a name. A file with the same columns is then set up automatically.</p>
            <form className="import-ai" onSubmit={saveProfile}>
              <input aria-label="Name for this mapping" maxLength={80} placeholder="e.g. My bank, current account" value={profileName} onChange={(e) => setProfileName(e.target.value)} />
              <button type="submit" disabled={!profileName.trim() || problems.length > 0}>
                Save mapping
              </button>
            </form>
            {profileNote && <p role="status">{profileNote}</p>}
          </section>
        </>
      )}
    </>
  )
}

// Everything that brings data into the app lives here: bank statements (read with the assistant and
// rules) and spreadsheets already in the app's own expense format. Both stay mounted, so switching tabs
// never loses a statement that is half set up.
export default function ImportPage({ options, onImported, onError }) {
  const [tab, setTab] = useState('statement')
  return (
    <>
      <h1>📥 Import</h1>
      <div className="tabs" role="tablist" aria-label="What to import">
        <button type="button" role="tab" aria-selected={tab === 'statement'} className={tab === 'statement' ? 'tab active' : 'tab'} onClick={() => setTab('statement')}>
          Bank statement
        </button>
        <button type="button" role="tab" aria-selected={tab === 'file'} className={tab === 'file' ? 'tab active' : 'tab'} onClick={() => setTab('file')}>
          Expense file
        </button>
      </div>
      <div hidden={tab !== 'statement'}>
        <StatementImport onImported={onImported} onError={onError} countBillsAsSpending={options?.count_bills_as_spending !== false} />
      </div>
      <div hidden={tab !== 'file'}>
        <ExpenseFileImport options={options} onImported={onImported} onError={onError} />
      </div>
    </>
  )
}

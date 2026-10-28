import { useState } from 'react'
import { money } from '../../format.js'
import InfoTip from '../InfoTip.jsx'
import { dayLabel, planByDay, shortDate } from '../../tripDays.js'
import './tripDays.css'

function ItemText({ item, currency }) {
  const { expense } = item
  const name = expense.description || expense.shop || expense.category
  return (
    <>
      {name}
      {item.cents === null ? (
        <span className="muted"> · no exchange rate, not counted</span>
      ) : (
        <>
          {' · '}
          {money(item.cents / 100, currency)}
          {item.spread && (
            <span className="muted">
              {' '}
              (1 of {item.parts} days of {money(item.totalCents / 100, currency)})
            </span>
          )}
        </>
      )}
    </>
  )
}

// The trip laid out as Day 1 … Day N, each expense on the day(s) it covers.
export default function TripDayPlan({ expenses, days, currency }) {
  const [showEmpty, setShowEmpty] = useState(false)
  const plan = planByDay(expenses, days)
  const withSpending = plan.days.filter((d) => d.items.length > 0)
  const shown = showEmpty ? plan.days : withSpending
  const empty = plan.days.length - withSpending.length

  return (
    <div data-testid="trip-day-plan">
      {shown.map((d) => (
        <section key={d.date} className="trip-day" aria-label={dayLabel(d)}>
          <div className="trip-day-head">
            <span>{dayLabel(d)}</span>
            <span>{d.items.length > 0 ? money(d.cents / 100, currency) : <span className="muted">nothing</span>}</span>
          </div>
          {d.items.length > 0 && (
            <ul>
              {d.items.map((item) => (
                <li key={`${item.expense.id}-${item.date}`}>
                  <ItemText item={item} currency={currency} />
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}

      {plan.outside.items.length > 0 && (
        <section className="trip-day" aria-label="Outside the trip dates">
          <div className="trip-day-head">
            <span>
              Not on a trip day
              <InfoTip label="Why are these not on a trip day?">
                These fall outside the trip’s dates (a stay paid before you left, say). Use ✎ in the Days column of the list
                to put them on the day or days they cover.
              </InfoTip>
            </span>
            <span>{money(plan.outside.cents / 100, currency)}</span>
          </div>
          <ul>
            {plan.outside.items.map((item) => (
              <li key={`${item.expense.id}-${item.date}`}>
                {shortDate(item.date)} · <ItemText item={item} currency={currency} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {empty > 0 && (
        <label className="subtitle trip-days-empty-toggle">
          <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} /> Show the {empty} day
          {empty === 1 ? '' : 's'} with nothing on them
        </label>
      )}
    </div>
  )
}

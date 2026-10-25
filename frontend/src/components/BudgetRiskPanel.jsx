import { money } from '../format.js'
import { RISK_COLORS, levelLabel, percent, describeRisk, headline, describeMethod } from '../budgetRisk.js'

// How likely each budget is to be exceeded by the end of its period, with the reason. Shown under the
// budget bars; hidden until there is a budget to talk about.
export default function BudgetRiskPanel({ risk }) {
  if (!risk || !risk.has_budgets) return null

  return (
    <section className="panel">
      <h2>🎲 Chance of going over</h2>
      <p data-testid="risk-headline">{headline(risk)}</p>
      <ul className="risk-list" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {risk.items.map((item) => (
          <li key={`${item.is_total ? 'total' : 'cat'}:${item.category}`} data-testid="risk-row" style={{ margin: '0.6rem 0' }}>
            <strong>{item.is_total ? `Overall (${item.period.toLowerCase()})` : item.category}</strong>{' '}
            <span className="subtitle">
              {money(item.spent)} of {money(item.limit)}
            </span>{' '}
            {item.available && (
              <strong style={{ color: RISK_COLORS[item.level] }} aria-label={`Chance of going over: ${percent(item)}`}>
                {percent(item)} · {levelLabel(item.level)}
              </strong>
            )}
            <div className="subtitle">{describeRisk(item, risk.min_periods)}</div>
          </li>
        ))}
      </ul>
      <p className="subtitle">{describeMethod(risk)}</p>
    </section>
  )
}

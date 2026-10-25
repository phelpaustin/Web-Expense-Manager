import { lazy, Suspense, useState } from 'react'
import ScopePicker from '../components/ScopePicker.jsx'
import CategoryBreakdown from '../components/CategoryBreakdown.jsx'
import CategoryChangePanel from '../components/CategoryChangePanel.jsx'
import SpendingMixPanel from '../components/SpendingMixPanel.jsx'
import ForecastPanel from '../components/ForecastPanel.jsx'
import { SpendingTrendChart, CashFlowChart } from '../components/Charts.jsx'

// Shops and Prices used to be pages of their own; they open inside the tab, as their own chunks.
const ShopsPage = lazy(() => import('./ShopsPage.jsx'))
const PriceTrackerPage = lazy(() => import('./PriceTrackerPage.jsx'))

export const INSIGHT_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'forecast', label: 'Forecast' },
  { key: 'categories', label: 'Categories' },
  { key: 'shops', label: 'Shops' },
  { key: 'prices', label: 'Prices' },
]
const TAB_KEYS = INSIGHT_TABS.map((t) => t.key)
// Shops and Prices look at everything, so the space picker would do nothing there.
const SCOPED = ['overview', 'forecast', 'categories']

// "Why, and what next?": the analysis that used to make the Dashboard one long page. The Dashboard keeps
// "how am I doing right now".
export default function InsightsPage({
  initialTab = 'overview',
  trends,
  metrics,
  categories = [],
  categoryMonths = [],
  groups,
  trips,
  dashboardScope,
  onSetDashboardScope,
  dashboardSpaceIds,
  onSetDashboardSpaceIds,
  onError,
}) {
  const [tab, setTab] = useState(TAB_KEYS.includes(initialTab) ? initialTab : 'overview')
  const scopeKey = `${dashboardScope}|${(dashboardSpaceIds || []).join(',')}`
  const hasCashFlow = metrics && metrics.cash_flow && metrics.cash_flow.length > 0

  return (
    <>
      {SCOPED.includes(tab) ? (
        <ScopePicker
          title="📈 Insights"
          groups={groups}
          trips={trips}
          dashboardScope={dashboardScope}
          onSetDashboardScope={onSetDashboardScope}
          dashboardSpaceIds={dashboardSpaceIds}
          onSetDashboardSpaceIds={onSetDashboardSpaceIds}
        />
      ) : (
        <h1 className="page-title">📈 Insights</h1>
      )}

      <div className="tabs" role="tablist" aria-label="Insights">
        {INSIGHT_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={tab === t.key ? 'tab active' : 'tab'}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <>
          {trends && (
            <section className="panel">
              <h2>📈 Spending trend</h2>
              <SpendingTrendChart data={trends.monthly} />
              <div className="trend-meta">
                {trends.change && (
                  <span>
                    vs previous month:{' '}
                    <strong className={trends.change.direction === 'up' ? 'up' : 'down'}>
                      {trends.change.direction === 'up' ? '▲' : '▼'} {Math.abs(trends.change.pct_change)}%
                    </strong>
                  </span>
                )}
              </div>
            </section>
          )}

          <SpendingMixPanel
            key={`mix|${scopeKey}`}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
          />

          {hasCashFlow && (
            <section className="panel">
              <h2>💸 Cash flow</h2>
              <CashFlowChart data={metrics.cash_flow} />
            </section>
          )}

          {metrics && (
            <section className="cards">
              <div className="card">
                <span className="card-label">Spend volatility</span>
                <span className="card-value">{metrics.volatility_cv}%</span>
              </div>
            </section>
          )}
        </>
      )}

      {tab === 'forecast' && (
        <ForecastPanel
          key={`forecast|${scopeKey}`}
          scope={dashboardScope}
          spaceIds={dashboardSpaceIds}
          refreshKey={trends}
        />
      )}

      {tab === 'categories' && (
        <>
          <CategoryChangePanel
            key={scopeKey}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
          />
          <CategoryBreakdown categories={categories} categoryMonths={categoryMonths} />
        </>
      )}

      {tab === 'shops' && (
        <Suspense fallback={<p className="subtitle">Loading…</p>}>
          <ShopsPage embedded onError={onError} />
        </Suspense>
      )}

      {tab === 'prices' && (
        <Suspense fallback={<p className="subtitle">Loading…</p>}>
          <PriceTrackerPage embedded onError={onError} />
        </Suspense>
      )}
    </>
  )
}

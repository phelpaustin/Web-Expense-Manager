import { lazy, Suspense, useEffect, useState } from 'react'
import { INSIGHT_TABS, insightTabFrom } from '../insightTabs.js'
import ScopePicker from '../components/ScopePicker.jsx'
import CategoryBreakdown from '../components/CategoryBreakdown.jsx'
import CategoryChangePanel from '../components/CategoryChangePanel.jsx'
import PeriodComparePanel from '../components/PeriodComparePanel.jsx'
import MoversPanel from '../components/MoversPanel.jsx'
import RecurringCostsPanel from '../components/RecurringCostsPanel.jsx'
import UnusualPanel from '../components/UnusualPanel.jsx'
import PatternsPanel from '../components/PatternsPanel.jsx'
import ReportPanel from '../components/ReportPanel.jsx'
import MembersPanel from '../components/MembersPanel.jsx'
import SpendingMixPanel from '../components/SpendingMixPanel.jsx'
import ForecastPanel from '../components/ForecastPanel.jsx'
import { SpendingTrendChart, CashFlowChart } from '../components/Charts.jsx'
import MonthDetailDialog from '../components/MonthDetailDialog.jsx'

// Shops and Prices used to be pages of their own; they open inside the tab, as their own chunks.
const ShopsPage = lazy(() => import('./ShopsPage.jsx'))
const PriceTrackerPage = lazy(() => import('./PriceTrackerPage.jsx'))

export { INSIGHT_TABS }
// Shops and Prices look at everything, so the space picker would do nothing there.
const SCOPED = ['overview', 'forecast', 'categories', 'report', 'members']

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
  options,
  onExpensesChanged,
  onTabChange,
}) {
  // The month the Overview panels talk about; null lets the server pick the last finished month.
  const [month, setMonth] = useState(null)
  const [detailMonth, setDetailMonth] = useState(null)
  const [tab, setTab] = useState(insightTabFrom(initialTab))
  // A sidebar link changes the address, which changes initialTab: follow it without remounting the page.
  useEffect(() => { setTab(insightTabFrom(initialTab)) }, [initialTab])
  const chooseTab = (key) => {
    setTab(key)
    if (onTabChange) onTabChange(key)
  }
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
            onClick={() => chooseTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <>
          <PeriodComparePanel
            key={`compare|${scopeKey}`}
            month={month}
            onMonthChange={setMonth}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
          />

          <MoversPanel
            key={`movers|${scopeKey}`}
            month={month}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
          />

          <PatternsPanel
            key={`patterns|${scopeKey}`}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
          />

          <UnusualPanel
            key={`unusual|${scopeKey}`}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
          />

          {trends && (
            <section className="panel">
              <h2>📈 Spending trend</h2>
              <SpendingTrendChart data={trends.monthly} onSelectMonth={setDetailMonth} />
              <p className="chart-hint">Click a month to see its expenses and income.</p>
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

          <RecurringCostsPanel refreshKey={trends} />

          <SpendingMixPanel
            key={`mix|${scopeKey}`}
            scope={dashboardScope}
            spaceIds={dashboardSpaceIds}
            refreshKey={trends}
            onSelectMonth={setDetailMonth}
          />

          {hasCashFlow && (
            <section className="panel">
              <h2>💸 Cash flow</h2>
              <CashFlowChart data={metrics.cash_flow} onSelectMonth={setDetailMonth} />
              <p className="chart-hint">Click a month to see its expenses and income.</p>
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

      {tab === 'report' && (
        <ReportPanel
          key={`report|${scopeKey}`}
          scope={dashboardScope}
          spaceIds={dashboardSpaceIds}
          refreshKey={trends}
        />
      )}

      {tab === 'members' && (
        <MembersPanel
          key={`members|${scopeKey}`}
          scope={dashboardScope}
          spaceIds={dashboardSpaceIds}
          refreshKey={trends}
        />
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

      {detailMonth && (
        <MonthDetailDialog
          month={detailMonth}
          scope={dashboardScope}
          spaceIds={dashboardSpaceIds}
          onChangeMonth={setDetailMonth}
          onClose={() => setDetailMonth(null)}
          options={options}
          groups={groups}
          trips={trips}
          onChanged={onExpensesChanged}
        />
      )}
    </>
  )
}

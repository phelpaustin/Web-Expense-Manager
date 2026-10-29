import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import AuthScreen from './AuthScreen.jsx'
import Layout from './Layout.jsx'
import { useAppData, EXPENSE_PARTS, PART } from './hooks/useAppData.js'
import { useAuth } from './hooks/useAuth.js'
import { useExpenseHandlers } from './hooks/useExpenseHandlers.js'
import { useIncomeHandlers } from './hooks/useIncomeHandlers.js'
import { useRecurringHandlers } from './hooks/useRecurringHandlers.js'
import { useBillsHandlers } from './hooks/useBillsHandlers.js'
import { useTripHandlers } from './hooks/useTripHandlers.js'
import { useGroupHandlers } from './hooks/useGroupHandlers.js'
import { useInvitationCount } from './hooks/useInvitationCount.js'
import { useBudgetHandlers } from './hooks/useBudgetHandlers.js'

// Each page is its own chunk: charts and rarely used screens are fetched when first visited,
// so the sign-in screen and the first paint download far less JavaScript.
const DashboardPage = lazy(() => import('./pages/DashboardPage.jsx'))
const SpendingPage = lazy(() => import('./pages/SpendingPage.jsx'))
const IncomePage = lazy(() => import('./pages/IncomePage.jsx'))
const RecurringPage = lazy(() => import('./pages/RecurringPage.jsx'))
const SavingsPage = lazy(() => import('./pages/SavingsPage.jsx'))
const SettingsPage = lazy(() => import('./pages/SettingsPage.jsx'))
const TripsPage = lazy(() => import('./pages/TripsPage.jsx'))
const InsightsPage = lazy(() => import('./pages/InsightsPage.jsx'))
const ImportPage = lazy(() => import('./pages/ImportPage.jsx'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage.jsx'))
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage.jsx'))
const UnsubscribePage = lazy(() => import('./pages/UnsubscribePage.jsx'))

const PageLoading = () => <p className="subtitle">Loading…</p>

// Settings opens on the tab named in the address (?tab=spaces), so links and the old /groups address land on it.
function SettingsRoute(props) {
  const [params] = useSearchParams()
  const tab = params.get('tab') || 'account'
  return <SettingsPage key={tab} {...props} initialTab={tab} />
}

// Insights opens on the tab named in the address (?tab=shops); /prices and /shops redirect to their tabs.
function InsightsRoute(props) {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'overview'
  // Choosing a tab puts it in the address, so the sidebar's sub-links show where you are and a reload stays put.
  return <InsightsPage {...props} initialTab={tab} onTabChange={(key) => setParams({ tab: key }, { replace: true })} />
}

// This component only wires fetched data + handlers (from the hooks below)
// into routes/pages — each page still receives all its data/handlers as
// plain props, unchanged. See src/hooks/ for the actual state and logic,
// split by domain (expenses/income/recurring/bills/trips/groups/budgets).
export default function App() {
  const data = useAppData()
  const auth = useAuth(data.loadAll, data.resetData, data.setError)
  const expense = useExpenseHandlers(data.loadAll, data.setError)
  const income = useIncomeHandlers(data.loadAll, data.setError)
  const recurring = useRecurringHandlers(data.loadAll, data.setError)
  const navigate = useNavigate()
  const bills = useBillsHandlers(data.loadAll, data.setError, data.setOptions, navigate, !!auth.user)
  const tripHandlers = useTripHandlers(data.loadAll, data.setError)
  const groupHandlers = useGroupHandlers(data.loadAll, data.setError)
  const budgetHandlers = useBudgetHandlers(data.loadAll, data.setError)
  const [invitationCount, setInvitationCount] = useInvitationCount(!!auth.user)

  if (!auth.authChecked) {
    return (
      <div className="container">
        <p>Loading…</p>
      </div>
    )
  }

  if (!auth.user) {
    return (
      <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/unsubscribe" element={<UnsubscribePage />} />
        <Route
          path="*"
          element={
            <div className="container">
              {auth.authError ? (
                <div className="auth-form">
                  <div className="auth-error">{auth.authError}</div>
                  <button type="button" onClick={auth.retryAuth} disabled={auth.loading}>
                    {auth.loading ? 'Trying…' : 'Try again'}
                  </button>
                </div>
              ) : (
                <AuthScreen onAuthed={auth.handleAuthed} sessionNotice={auth.sessionNotice} />
              )}
            </div>
          }
        />
      </Routes>
      </Suspense>
    )
  }

  return (
    <Suspense fallback={<PageLoading />}>
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/unsubscribe" element={<UnsubscribePage />} />
      <Route
        element={
          <Layout
            user={auth.user}
            onLogout={auth.handleLogout}
            error={data.error}
            loading={auth.loading}
            alerts={data.alerts}
            options={data.options}
            onDisplayCurrencyChange={data.changeDisplayCurrency}
            invitationCount={invitationCount}
            onUploadReceipt={bills.actions.uploadBill}
          />
        }
      >
        <Route
          index
          element={
            <DashboardPage
              currencies={data.options.currencies}
              displayCurrency={data.options.display_currency}
              summary={data.summary}
              budgets={data.budgets}
              trends={data.trends}
              onSetBudget={budgetHandlers.handleSetBudget}
              onDeleteBudget={budgetHandlers.handleDeleteBudget}
              metrics={data.metrics}
              periodStatus={data.periodStatus}
              budgetRisk={data.budgetRisk}
              budgetConfig={data.budgetConfig}
              onSetBudgetConfig={budgetHandlers.handleSetBudgetConfig}
              groups={data.groups}
              trips={data.trips}
              dashboardScope={data.dashboardScope}
              onSetDashboardScope={data.handleSetDashboardScope}
              dashboardSpaceIds={data.dashboardSpaceIds}
              onSetDashboardSpaceIds={data.handleSetDashboardSpaceIds}
              options={data.options}
              onExpensesChanged={() => data.loadAll(EXPENSE_PARTS)}
            />
          }
        />
        <Route
          path="spending"
          element={
            <SpendingPage
              bills={bills}
              expenseProps={{
                form: expense.form,
                setForm: expense.setForm,
                saving: expense.saving,
                onAdd: expense.handleAdd,
                onAddBill: expense.handleAddBill,
                editingId: expense.editingId,
                editForm: expense.editForm,
                setEditForm: expense.setEditForm,
                startEdit: expense.startEdit,
                cancelEdit: expense.cancelEdit,
                saveEdit: expense.saveEdit,
                onDelete: expense.handleDelete,
                onBulkUpdate: expense.handleBulkUpdate,
                onBulkCopy: expense.handleBulkCopy,
                options: data.options,
                trips: data.trips,
                groups: data.groups,
                onError: data.setError,
              }}
            />
          }
        />
        {/* Expenses and Bills became two views of Spending; old links and bookmarks still land there. */}
        <Route path="expenses" element={<Navigate to="/spending?view=items" replace />} />
        <Route path="bills" element={<Navigate to="/spending?view=receipts" replace />} />
        <Route
          path="income"
          element={
            <IncomePage
              income={data.income}
              incomeSummary={data.incomeSummary}
              incomeForm={income.incomeForm}
              setIncomeForm={income.setIncomeForm}
              savingIncome={income.savingIncome}
              onAddIncome={income.handleAddIncome}
              onDeleteIncome={income.handleDeleteIncome}
              currencies={data.options.currencies}
              baseCurrency={data.options.base_currency}
            />
          }
        />
        <Route
          path="recurring"
          element={
            <RecurringPage
              recurring={data.recurring}
              recurringForm={recurring.recurringForm}
              setRecurringForm={recurring.setRecurringForm}
              savingRecurring={recurring.savingRecurring}
              onAdd={recurring.handleAddRecurring}
              onApply={recurring.handleApplyRecurring}
              onApplyDue={recurring.handleApplyDue}
              onDelete={recurring.handleDeleteRecurring}
              onUpdate={recurring.handleUpdateRecurring}
              onBackfill={recurring.handleBackfillRecurring}
              currencies={data.options.currencies}
              baseCurrency={data.options.base_currency}
            />
          }
        />
        <Route
          path="savings"
          element={<SavingsPage currencies={data.options.currencies} baseCurrency={data.options.base_currency} />}
        />
        <Route
          path="settings"
          element={
            <SettingsRoute
              user={auth.user}
              options={data.options}
              onOptionsUpdated={data.setOptions}
              onCurrencyChanged={data.loadAll}
              onDisplayCurrencyChange={data.changeDisplayCurrency}
              onError={data.setError}
              onDeleteAccount={auth.handleDeleteAccount}
              onExport={expense.handleExport}
              spaces={{
                groups: data.groups,
                currencies: data.options.currencies,
                baseCurrency: data.options.base_currency,
                onCreateGroup: groupHandlers.handleCreateGroup,
                onDeleteGroup: groupHandlers.handleDeleteGroup,
                onLeaveGroup: groupHandlers.handleLeaveGroup,
                onRefresh: () => data.loadAll(EXPENSE_PARTS),
                onInvitationsChange: setInvitationCount,
              }}
            />
          }
        />
        <Route
          path="trips"
          element={
            <TripsPage
              trips={data.trips}
              groups={data.groups}
              onAddTrip={tripHandlers.handleAddTrip}
              onUpdateTrip={tripHandlers.handleUpdateTrip}
              onDeleteTrip={tripHandlers.handleDeleteTrip}
              onRefresh={() => data.loadAll(EXPENSE_PARTS)}
              onError={data.setError}
            />
          }
        />
        <Route
          path="insights"
          element={
            <InsightsRoute
              trends={data.trends}
              metrics={data.metrics}
              categories={data.categories}
              categoryMonths={data.categoryMonths}
              groups={data.groups}
              trips={data.trips}
              dashboardScope={data.dashboardScope}
              onSetDashboardScope={data.handleSetDashboardScope}
              dashboardSpaceIds={data.dashboardSpaceIds}
              onSetDashboardSpaceIds={data.handleSetDashboardSpaceIds}
              onError={data.setError}
              options={data.options}
              onExpensesChanged={() => data.loadAll(EXPENSE_PARTS)}
            />
          }
        />
        {/* Prices and Shops became tabs of Insights; old links and bookmarks still land there. */}
        <Route path="prices" element={<Navigate to="/insights?tab=prices" replace />} />
        <Route path="shops" element={<Navigate to="/insights?tab=shops" replace />} />
        <Route
          path="import"
          element={<ImportPage options={data.options} onImported={() => data.loadAll([...EXPENSE_PARTS, PART.INCOME])} onError={data.setError} />}
        />
        {/* Expense Spaces moved into Settings; old links and bookmarks still land there. */}
        <Route path="groups" element={<Navigate to="/settings?tab=spaces" replace />} />
      </Route>
    </Routes>
    </Suspense>
  )
}

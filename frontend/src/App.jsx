import { lazy, Suspense } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
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
import { useBudgetHandlers } from './hooks/useBudgetHandlers.js'

// Each page is its own chunk: charts and rarely used screens are fetched when first visited,
// so the sign-in screen and the first paint download far less JavaScript.
const DashboardPage = lazy(() => import('./pages/DashboardPage.jsx'))
const ExpensesPage = lazy(() => import('./pages/ExpensesPage.jsx'))
const IncomePage = lazy(() => import('./pages/IncomePage.jsx'))
const RecurringPage = lazy(() => import('./pages/RecurringPage.jsx'))
const BillsPage = lazy(() => import('./pages/BillsPage.jsx'))
const SettingsPage = lazy(() => import('./pages/SettingsPage.jsx'))
const TripsPage = lazy(() => import('./pages/TripsPage.jsx'))
const PriceTrackerPage = lazy(() => import('./pages/PriceTrackerPage.jsx'))
const ShopsPage = lazy(() => import('./pages/ShopsPage.jsx'))
const ImportPage = lazy(() => import('./pages/ImportPage.jsx'))
const GroupsPage = lazy(() => import('./pages/GroupsPage.jsx'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage.jsx'))
const VerifyEmailPage = lazy(() => import('./pages/VerifyEmailPage.jsx'))
const UnsubscribePage = lazy(() => import('./pages/UnsubscribePage.jsx'))

const PageLoading = () => <p className="subtitle">Loading…</p>

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
              categories={data.categories}
              categoryMonths={data.categoryMonths}
              onSetBudget={budgetHandlers.handleSetBudget}
              onDeleteBudget={budgetHandlers.handleDeleteBudget}
              metrics={data.metrics}
              periodStatus={data.periodStatus}
              budgetConfig={data.budgetConfig}
              onSetBudgetConfig={budgetHandlers.handleSetBudgetConfig}
              groups={data.groups}
              trips={data.trips}
              dashboardScope={data.dashboardScope}
              onSetDashboardScope={data.handleSetDashboardScope}
              dashboardSpaceIds={data.dashboardSpaceIds}
              onSetDashboardSpaceIds={data.handleSetDashboardSpaceIds}
            />
          }
        />
        <Route
          path="expenses"
          element={
            <ExpensesPage
              form={expense.form}
              setForm={expense.setForm}
              saving={expense.saving}
              onAdd={expense.handleAdd}
              onAddBill={expense.handleAddBill}
              editingId={expense.editingId}
              editForm={expense.editForm}
              setEditForm={expense.setEditForm}
              startEdit={expense.startEdit}
              cancelEdit={expense.cancelEdit}
              saveEdit={expense.saveEdit}
              onDelete={expense.handleDelete}
              onBulkUpdate={expense.handleBulkUpdate}
              options={data.options}
              onExport={expense.handleExport}
              trips={data.trips}
              groups={data.groups}
              onError={data.setError}
            />
          }
        />
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
          path="bills"
          element={
            <BillsPage state={bills} options={data.options} />
          }
        />
        <Route
          path="settings"
          element={
            <SettingsPage
              user={auth.user}
              options={data.options}
              onOptionsUpdated={data.setOptions}
              onCurrencyChanged={data.loadAll}
              onDisplayCurrencyChange={data.changeDisplayCurrency}
              onError={data.setError}
              onDeleteAccount={auth.handleDeleteAccount}
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
        <Route path="prices" element={<PriceTrackerPage onError={data.setError} />} />
        <Route path="shops" element={<ShopsPage onError={data.setError} />} />
        <Route
          path="import"
          element={<ImportPage options={data.options} onImported={() => data.loadAll([...EXPENSE_PARTS, PART.INCOME])} onError={data.setError} />}
        />
        <Route
          path="groups"
          element={
            <GroupsPage
              groups={data.groups}
              currencies={data.options.currencies}
              baseCurrency={data.options.base_currency}
              onCreateGroup={groupHandlers.handleCreateGroup}
              onDeleteGroup={groupHandlers.handleDeleteGroup}
              onLeaveGroup={groupHandlers.handleLeaveGroup}
              onRefresh={() => data.loadAll(EXPENSE_PARTS)}
              onError={data.setError}
            />
          }
        />
      </Route>
    </Routes>
    </Suspense>
  )
}

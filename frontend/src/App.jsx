import { Routes, Route, useNavigate } from 'react-router-dom'
import AuthScreen from './AuthScreen.jsx'
import Layout from './Layout.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import ExpensesPage from './pages/ExpensesPage.jsx'
import IncomePage from './pages/IncomePage.jsx'
import RecurringPage from './pages/RecurringPage.jsx'
import BillsPage from './pages/BillsPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import TripsPage from './pages/TripsPage.jsx'
import PriceTrackerPage from './pages/PriceTrackerPage.jsx'
import GroupsPage from './pages/GroupsPage.jsx'
import ResetPasswordPage from './pages/ResetPasswordPage.jsx'
import VerifyEmailPage from './pages/VerifyEmailPage.jsx'
import UnsubscribePage from './pages/UnsubscribePage.jsx'
import { useAppData } from './hooks/useAppData.js'
import { useAuth } from './hooks/useAuth.js'
import { useExpenseHandlers } from './hooks/useExpenseHandlers.js'
import { useIncomeHandlers } from './hooks/useIncomeHandlers.js'
import { useRecurringHandlers } from './hooks/useRecurringHandlers.js'
import { useBillsHandlers } from './hooks/useBillsHandlers.js'
import { useTripHandlers } from './hooks/useTripHandlers.js'
import { useGroupHandlers } from './hooks/useGroupHandlers.js'
import { useBudgetHandlers } from './hooks/useBudgetHandlers.js'

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
    )
  }

  return (
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
              options={data.options}
              onImport={expense.handleImport}
              onExport={expense.handleExport}
              importCurrency={expense.importCurrency}
              setImportCurrency={expense.setImportCurrency}
              onAddRow={expense.handleAddRow}
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
              onRefresh={data.loadAll}
              onError={data.setError}
            />
          }
        />
        <Route path="prices" element={<PriceTrackerPage onError={data.setError} />} />
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
              onRefresh={data.loadAll}
              onError={data.setError}
            />
          }
        />
      </Route>
    </Routes>
  )
}

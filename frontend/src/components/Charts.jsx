import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  BarChart,
  Bar,
  Legend,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { money } from '../format.js'

const ACCENT = '#6d7bff'
const GREEN = '#10b981'
const PIE = ['#6d7bff', '#a674ff', '#38bdf8', '#10b981', '#f59e0b', '#f472b6', '#f87171', '#34d399', '#818cf8', '#fb923c']
const axis = { stroke: '#9aa3b8', fontSize: 12 }

function CurrencyTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  return (
    <div className="chart-tip">
      {label && <div className="chart-tip-label">{label}</div>}
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color || p.payload?.fill }}>
          {p.name}: {money(p.value)}
        </div>
      ))}
    </div>
  )
}

export function SpendingTrendChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} />
            <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
        <XAxis dataKey="month" {...axis} />
        <YAxis {...axis} width={52} />
        <Tooltip content={<CurrencyTooltip />} />
        <Area type="monotone" dataKey="total" name="Spent" stroke={ACCENT} strokeWidth={2} fill="url(#spendGrad)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function CashFlowChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e6e8f2" />
        <XAxis dataKey="month" {...axis} />
        <YAxis {...axis} width={52} />
        <Tooltip content={<CurrencyTooltip />} />
        <Legend />
        <Bar dataKey="income" name="Income" fill={GREEN} radius={[4, 4, 0, 0]} />
        <Bar dataKey="expenses" name="Expenses" fill={ACCENT} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function CategoryDonut({ data }) {
  const chartData = data.map((c) => ({ name: c.category, value: c.total }))
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie data={chartData} dataKey="value" nameKey="name" innerRadius={62} outerRadius={100} paddingAngle={2}>
          {chartData.map((_, i) => (
            <Cell key={i} fill={PIE[i % PIE.length]} />
          ))}
        </Pie>
        <Tooltip content={<CurrencyTooltip />} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}

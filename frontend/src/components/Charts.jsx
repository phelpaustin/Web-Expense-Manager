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

// Clicking (or tapping) a month calls onSelectMonth("2025-01"). Recharts reports the clicked x label.
function monthClick(onSelectMonth) {
  if (!onSelectMonth) return undefined
  return (state) => {
    const month = state?.activeLabel
    if (month) onSelectMonth(String(month))
  }
}

const clickable = (onSelectMonth) => (onSelectMonth ? { cursor: 'pointer' } : undefined)

export function SpendingTrendChart({ data, onSelectMonth }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart
        data={data}
        margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        onClick={monthClick(onSelectMonth)}
        style={clickable(onSelectMonth)}
      >
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

export function CashFlowChart({ data, onSelectMonth }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart
        data={data}
        margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        onClick={monthClick(onSelectMonth)}
        style={clickable(onSelectMonth)}
      >
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
  // The legend lives outside the chart: with many categories it wraps onto several rows, and inside
  // a fixed-height chart it squeezed the ring until its top was cut off.
  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
          <Pie data={chartData} dataKey="value" nameKey="name" innerRadius={62} outerRadius={100} paddingAngle={2}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={PIE[i % PIE.length]} />
            ))}
          </Pie>
          <Tooltip content={<CurrencyTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <ul className="donut-legend" data-testid="category-legend">
        {chartData.map((d, i) => (
          <li key={d.name}>
            <span className="donut-swatch" style={{ background: PIE[i % PIE.length] }} />
            {d.name}
          </li>
        ))}
      </ul>
    </div>
  )
}

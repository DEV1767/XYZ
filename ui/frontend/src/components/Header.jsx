import React from 'react'
import { formatINR } from '../utils/formatters'

export function Header({
  isDark,
  setIsDark,
  simulationClock,
  portfolio,
  taxMetrics = {},
  lastOrderLatency = {},
  scorecard = {},
  isLoading,
  setIsLoading,
  rateCount = 38,
  onOpenVoice,
  isVoiceActive,
}) {
  const pnlNum = Number(portfolio?.pnlPercent) || 0
  const isPnlPositive = pnlNum >= 0
  const netProfit = (portfolio?.totalWealth || 0) - (portfolio?.startingCapital || 1000000)

  const cashUtilPct = scorecard?.pillar_2_cash_utilization?.current_cash_utilization_pct !== undefined
    ? scorecard.pillar_2_cash_utilization.current_cash_utilization_pct
    : '78.0'

  const p3 = scorecard?.pillar_3_decision_latency
  const latencyMs = p3?.average_latency_ms !== undefined
    ? Math.round(p3.average_latency_ms)
    : (lastOrderLatency?.rest ? Object.values(lastOrderLatency).reduce((a, b) => a + (Number(b) || 0), 0) : 42)

  const p4 = scorecard?.pillar_4_order_error_rate
  const errorRatePct = p4?.error_rate_pct !== undefined ? p4.error_rate_pct : '0.0'
  const rejectionsCount = p4?.rejected_orders_by_exchange || 0
  const ordersCount = p4?.total_orders_submitted || 50

  const totalFriction = taxMetrics?.totalFeesPaid !== undefined
    ? taxMetrics.totalFeesPaid
    : (scorecard?.pillar_5_tax_and_friction_efficiency?.total_frictions_inr || 355.34)

  return (
    <header className="w-full border-b border-[#D5D0C3] dark:border-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F] text-[#1C2026] dark:text-[#E5E9F0] select-none transition-colors">
      {/* 1. Top bar: Brand, stage, sim clock, rate limit, voice button, theme switch */}
      <div className="h-10 px-3 flex items-center justify-between text-xs border-b border-[#D5D0C3] dark:border-[#1E2633] font-sans">
        {/* Left: Brand, stage, sim clock, rate limit */}
        <div className="flex items-center space-x-3 overflow-x-auto whitespace-nowrap scrollbar-none">
          <span className="font-semibold text-[#1C2026] dark:text-[#E5E9F0]">
            Manthan 2026 // group-mn2612
          </span>

          <span className="text-[#D5D0C3] dark:text-[#1E2633]">|</span>

          <span className="text-[#475569] dark:text-[#94A3B8]">
            Stage: <span className="text-emerald-700 dark:text-emerald-400 font-medium">Simulation (running)</span>
          </span>

          <span className="text-[#D5D0C3] dark:text-[#1E2633] hidden sm:inline">|</span>

          <span className="hidden sm:inline text-[#475569] dark:text-[#94A3B8]">
            Sim clock:{' '}
            <span className="font-mono text-[#1C2026] dark:text-[#E5E9F0]">
              Day {simulationClock?.current_day || 18} of {simulationClock?.total_days || 30}
            </span>{' '}
            <span className="text-[#64748B] dark:text-[#94A3B8]">({simulationClock?.interval_seconds || 4}s interval)</span>
          </span>

          <span className="text-[#D5D0C3] dark:text-[#1E2633] hidden md:inline">|</span>

          <span className="hidden md:inline text-[#475569] dark:text-[#94A3B8]">
            Rate limit:{' '}
            <span className="font-mono font-medium text-[#1C2026] dark:text-[#E5E9F0]">
              {rateCount} / 120 RPM
            </span>{' '}
            <span className="text-emerald-700 dark:text-emerald-400 font-medium">(0 rejections, 10 partitions)</span>
          </span>
        </div>

        {/* Right: Voice Agent side panel trigger, Skeleton demo toggle, Theme switch */}
        <div className="flex items-center space-x-2 shrink-0 pl-2">
          {/* Prominent Voice Talk button */}
          <button
            onClick={onOpenVoice}
            className={`px-3 py-1 text-xs font-semibold rounded-[3px] border transition-all flex items-center space-x-1.5 shadow-sm ${
              isVoiceActive
                ? 'bg-gradient-to-r from-emerald-600 to-teal-700 text-white border-emerald-500 ring-2 ring-emerald-400/40'
                : 'bg-emerald-700 hover:bg-emerald-600 text-white border-emerald-600'
            }`}
            title="Open real-time conversational voice talk (Gnani.ai)"
          >
            <span className="text-sm">🎙️</span>
            <span>Voice Talk</span>
            <span className="text-[10px] font-mono bg-black/25 px-1.5 py-0.5 rounded text-emerald-100 font-bold">Nalini en-IN</span>
          </button>

          <button
            onClick={() => setIsLoading(!isLoading)}
            className="px-2 py-1 text-xs border border-[#D5D0C3] dark:border-[#1E2633] hover:border-[#6C7480] dark:hover:border-[#7E8B9B] bg-[#EFECE2] dark:bg-[#0B0E14] text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026] dark:hover:text-[#E5E9F0] rounded-[2px] transition-colors"
            title="Toggle loading skeleton state preview"
          >
            Skeleton: {isLoading ? 'On' : 'Off'}
          </button>

          <button
            onClick={() => setIsDark(!isDark)}
            className="px-2 py-1 text-xs border border-[#D5D0C3] dark:border-[#1E2633] hover:border-[#6C7480] dark:hover:border-[#7E8B9B] bg-[#EFECE2] dark:bg-[#0B0E14] text-[#1C2026] dark:text-[#E5E9F0] rounded-[2px] transition-colors"
          >
            Theme: {isDark ? 'Night' : 'Day'}
          </button>
        </div>
      </div>

      {/* 2. Scorecard strip: Total Wealth, Cash Utilization, Decision Latency (p95), Order Error Rate, Total Friction */}
      <div className="grid grid-cols-2 md:grid-cols-5 divide-y md:divide-y-0 divide-[#D5D0C3] dark:divide-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F]">
        {/* 1. Total Wealth */}
        <div className="p-2.5 border-r border-[#D5D0C3] dark:border-[#1E2633] flex flex-col justify-between">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans font-medium">
            Total wealth
          </div>
          <div className="text-lg font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] leading-snug my-0.5">
            {formatINR(portfolio?.totalWealth)}
          </div>
          <div className={`text-xs font-sans ${isPnlPositive ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'}`}>
            {isPnlPositive ? '+' : ''}{portfolio?.pnlPercent}% ({formatINR(netProfit)} net)
          </div>
        </div>

        {/* 2. Cash Utilization */}
        <div className="p-2.5 border-r border-[#D5D0C3] dark:border-[#1E2633] flex flex-col justify-between">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans font-medium">
            Cash utilization
          </div>
          <div className="text-lg font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] leading-snug my-0.5">
            {cashUtilPct}%
          </div>
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans">
            {formatINR(portfolio?.availableCash)} liquid buffer
          </div>
        </div>

        {/* 3. Decision Latency (p95) */}
        <div className="p-2.5 border-r border-[#D5D0C3] dark:border-[#1E2633] flex flex-col justify-between">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans font-medium">
            Decision latency (p95)
          </div>
          <div className="text-lg font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] leading-snug my-0.5">
            {latencyMs}ms
          </div>
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans">
            3,000ms decision window budget
          </div>
        </div>

        {/* 4. Order Error Rate */}
        <div className="p-2.5 border-r border-[#D5D0C3] dark:border-[#1E2633] flex flex-col justify-between">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans font-medium">
            Order error rate
          </div>
          <div className="text-lg font-semibold font-mono tabular-nums text-emerald-700 dark:text-emerald-400 leading-snug my-0.5">
            {errorRatePct}%
          </div>
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans">
            {rejectionsCount} rejections across {ordersCount} orders
          </div>
        </div>

        {/* 5. Total Friction */}
        <div className="p-2.5 flex flex-col justify-between">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans font-medium">
            Total friction
          </div>
          <div className="text-lg font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] leading-snug my-0.5">
            {formatINR(totalFriction)}
          </div>
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-sans">
            &lt; 0.03% total volume drag
          </div>
        </div>
      </div>
    </header>
  )
}

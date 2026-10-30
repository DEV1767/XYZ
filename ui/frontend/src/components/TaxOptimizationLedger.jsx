import React, { useState } from 'react'
import { formatINR } from '../utils/formatters'

export function TaxOptimizationLedger({
  taxMetrics = {
    grossProfit: 82400.0,
    realizedLosses: 14200.0,
    taxableBase: 68200.0,
    netTaxPayable: 10230.0,
    totalFeesPaid: 355.34,
  },
  longTermLots = [], // Empty by default to display "No long-term lots yet"
  state = 'normal', // 'normal' | 'loading' | 'empty' | 'error' | 'stale'
}) {
  const [panelState, setPanelState] = useState(state)

  // Math Chain (Requirement G.1):
  // Gross gains - losses (Sec 70/71) = net taxable base * 15% = tax payable.
  const grossGains = taxMetrics.grossProfit || 82400.0
  const losses = taxMetrics.realizedLosses || 14200.0
  const netTaxableBase = grossGains - losses // 68,200.00
  const taxPayable = netTaxableBase * 0.15 // 10,230.00 (Do not subtract credit a second time)
  const totalFees = taxMetrics.totalFeesPaid || 355.34
  const netPnLAfterFeesAndTax = grossGains - losses - taxPayable - totalFees // ₹57,614.66

  // 6 Stocks Allocation with ONE blue-grey tone with different lightness (Requirement H)
  // All 6 stocks in legend
  const stockAllocations = [
    { ticker: 'PLNX', weight: 26, bgClass: 'bg-slate-800 dark:bg-slate-300', textLight: 'text-slate-800 dark:text-slate-200' },
    { ticker: 'AERX', weight: 22, bgClass: 'bg-slate-700 dark:bg-slate-400', textLight: 'text-slate-700 dark:text-slate-300' },
    { ticker: 'DSNY', weight: 18, bgClass: 'bg-slate-600 dark:bg-slate-500', textLight: 'text-slate-600 dark:text-slate-400' },
    { ticker: 'HMDP', weight: 14, bgClass: 'bg-slate-500 dark:bg-slate-600', textLight: 'text-slate-500 dark:text-slate-500' },
    { ticker: 'BLUX', weight: 10, bgClass: 'bg-slate-400 dark:bg-slate-700', textLight: 'text-slate-400 dark:text-slate-600' },
    { ticker: 'ORCX', weight: 10, bgClass: 'bg-slate-300 dark:bg-slate-800', textLight: 'text-slate-300 dark:text-slate-700' },
  ]

  if (panelState === 'loading') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-3 text-xs font-sans animate-pulse min-h-[260px]">
        <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-1/3 mb-3"></div>
        <div className="space-y-2">
          <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
          <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
          <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
        </div>
      </div>
    )
  }

  if (panelState === 'error') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-4 text-xs font-sans min-h-[260px] flex flex-col justify-between">
        <div className="font-semibold text-rose-700 dark:text-rose-400">Tax ledger</div>
        <div className="py-8 text-center text-[#475569] dark:text-[#94A3B8]">
          <p className="text-rose-700 dark:text-rose-400 font-medium">Failed to compute tax offsets for current assessment year</p>
          <button
            onClick={() => setPanelState('normal')}
            className="mt-3 px-3 py-1 text-xs border border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2] dark:bg-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0]"
          >
            Recalculate
          </button>
        </div>
        <div className="text-[11px] text-[#64748B]">State: error</div>
      </div>
    )
  }

  return (
    <div className={`w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] p-3 font-sans text-xs select-none transition-colors rounded-[2px] flex flex-col justify-between ${
      panelState === 'stale' ? 'opacity-70' : ''
    }`}>
      {/* 1. Header */}
      <div className="flex items-center justify-between pb-2 border-b border-[#D5D0C3] dark:border-[#1E2633]">
        <div>
          <div className="font-semibold text-sm text-[#1C2026] dark:text-[#E5E9F0]">
            Tax ledger &amp; frictions engine
          </div>
          <p className="text-xs text-[#475569] dark:text-[#94A3B8] mt-0.5">
            Income-tax Act Sections 70 &amp; 71 capital loss offsetting chain
          </p>
        </div>

        <div className="text-right">
          <span className="text-xs text-[#475569] dark:text-[#94A3B8] block">Assessment year</span>
          <span className="font-semibold font-mono text-[#1C2026] dark:text-[#E5E9F0]">
            AY 2026-27
          </span>
        </div>
      </div>

      {/* 2. Primary Math Chain (Requirement G.1) */}
      <div className="my-2 p-2.5 bg-[#EFECE2]/50 dark:bg-[#0B0E14] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] space-y-1.5 font-mono text-xs">
        <div className="flex justify-between items-center text-[#475569] dark:text-[#94A3B8]">
          <span className="font-sans text-xs">Gross gains</span>
          <span className="font-semibold tabular-nums text-[#1C2026] dark:text-[#E5E9F0]">
            {formatINR(grossGains)}
          </span>
        </div>

        <div className="flex justify-between items-center text-[#475569] dark:text-[#94A3B8]">
          <span className="font-sans text-xs">Minus losses (Sections 70 and 71)</span>
          <span className="font-semibold tabular-nums text-rose-700 dark:text-rose-400">
            -{formatINR(losses)}
          </span>
        </div>

        <div className="flex justify-between items-center border-t border-[#D5D0C3] dark:border-[#1E2633] pt-1 text-[#1C2026] dark:text-[#E5E9F0]">
          <span className="font-sans text-xs font-medium">Equals net taxable base</span>
          <span className="font-semibold tabular-nums">
            {formatINR(netTaxableBase)}
          </span>
        </div>

        <div className="flex justify-between items-center text-[#475569] dark:text-[#94A3B8]">
          <span className="font-sans text-xs">Times 15 percent (STCG rate)</span>
          <span className="font-mono tabular-nums">× 15.0%</span>
        </div>

        <div className="flex justify-between items-center border-t border-[#D5D0C3] dark:border-[#1E2633] pt-1 font-semibold text-[#1C2026] dark:text-[#E5E9F0]">
          <span className="font-sans text-xs">Equals tax payable</span>
          <span className="tabular-nums">
            {formatINR(taxPayable)}
          </span>
        </div>
      </div>

      {/* 3. Section 112A Exemption & Market Frictions (Requirement G.2 & G.3) */}
      <div className="grid grid-cols-2 gap-2 my-1 text-xs">
        {/* Section 112A exemption status */}
        <div className="p-2 bg-[#EFECE2]/30 dark:bg-[#0B0E14] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px]">
          <span className="text-xs text-[#475569] dark:text-[#94A3B8] block">Section 112A exemption</span>
          <span className="font-medium text-[#1C2026] dark:text-[#E5E9F0] mt-0.5 block">
            {longTermLots && longTermLots.length > 0
              ? '₹1,00,000 exemption lot active'
              : 'No long-term lots yet'}
          </span>
        </div>

        {/* Flat fees & friction */}
        <div className="p-2 bg-[#EFECE2]/30 dark:bg-[#0B0E14] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px]">
          <span className="text-xs text-[#475569] dark:text-[#94A3B8] block">Execution friction</span>
          <span className="font-medium text-[#1C2026] dark:text-[#E5E9F0] mt-0.5 block font-mono">
            Brokerage {formatINR(20.0)}, DP {formatINR(15.34)} (<span className="text-emerald-700 dark:text-emerald-400 font-sans">&lt; 0.03%</span>)
          </span>
        </div>
      </div>

      {/* 4. Single Bottom Line: Net P&L after fees and tax (Requirement G.4) */}
      <div className="p-2 bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] flex items-center justify-between text-xs my-1 font-sans">
        <span className="font-medium text-[#1C2026] dark:text-[#E5E9F0]">
          Net P&amp;L after fees and tax
        </span>
        <span className="font-semibold font-mono tabular-nums text-emerald-700 dark:text-emerald-400 text-sm">
          {formatINR(netPnLAfterFeesAndTax)}
        </span>
      </div>

      {/* 5. Allocation Bar: One blue-grey tone with different lightness per stock, all six stocks in legend (Requirement H) */}
      <div className="mt-2 pt-2 border-t border-[#D5D0C3] dark:border-[#1E2633] space-y-1.5">
        <div className="flex justify-between items-center text-xs text-[#475569] dark:text-[#94A3B8]">
          <span>Portfolio allocation</span>
          <span className="font-mono text-[#64748B]">All 6 positions active</span>
        </div>

        {/* Continuous Segmented Bar */}
        <div className="h-3.5 w-full border border-[#D5D0C3] dark:border-[#1E2633] rounded-[1px] flex overflow-hidden">
          {stockAllocations.map((st) => (
            <div
              key={st.ticker}
              style={{ width: `${st.weight}%` }}
              className={`${st.bgClass} h-full transition-all`}
              title={`${st.ticker}: ${st.weight}%`}
            ></div>
          ))}
        </div>

        {/* Legend showing ALL six stocks (Requirement H) */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-1 pt-0.5 text-xs font-mono">
          {stockAllocations.map((st) => (
            <div key={st.ticker} className="flex items-center space-x-1">
              <span className={`w-2 h-2 rounded-[1px] ${st.bgClass} shrink-0`}></span>
              <span className="text-[#1C2026] dark:text-[#E5E9F0]">
                {st.ticker} {st.weight}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

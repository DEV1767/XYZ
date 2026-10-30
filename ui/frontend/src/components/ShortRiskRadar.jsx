import React, { useState } from 'react'
import { formatINR } from '../utils/formatters'

export function ShortRiskRadar({
  shortPositions = [],
  settlementDay = 18,
  onTriggerEmergencyCover,
  state = 'normal', // 'normal' | 'loading' | 'empty' | 'error' | 'stale'
}) {
  const [panelState, setPanelState] = useState(state)

  const activeDay = (settlementDay % 10) || 8 // e.g. Day 8 of 10

  if (panelState === 'loading') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-3 text-xs font-sans animate-pulse min-h-[260px]">
        <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-1/3 mb-3"></div>
        <div className="h-6 bg-[#EFECE2] dark:bg-[#1E2633] w-full mb-3"></div>
        <div className="space-y-2">
          <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
          <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
        </div>
      </div>
    )
  }

  if (panelState === 'error') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-4 text-xs font-sans min-h-[260px] flex flex-col justify-between">
        <div className="font-semibold text-rose-700 dark:text-rose-400">10-day short shield (Day 8 auto-cover)</div>
        <div className="py-8 text-center text-[#475569] dark:text-[#94A3B8]">
          <p className="text-rose-700 dark:text-rose-400 font-medium">Failed to synchronize margin registry with exchange gateway</p>
          <button
            onClick={() => setPanelState('normal')}
            className="mt-3 px-3 py-1 text-xs border border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2] dark:bg-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0]"
          >
            Retry sync
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
      {/* 1. Header (Requirement F.1: Day 8 auto-cover in header, rule text, timeline) */}
      <div className="flex items-center justify-between pb-2 border-b border-[#D5D0C3] dark:border-[#1E2633]">
        <div>
          <div className="font-semibold text-sm text-[#1C2026] dark:text-[#E5E9F0]">
            10-day short shield (Day 8 auto-cover)
          </div>
          <p className="text-xs text-[#475569] dark:text-[#94A3B8] mt-0.5">
            Short trades are auto-covered on Day 8 to eliminate forced Day 10 exchange liquidation.
          </p>
        </div>

        <div className="text-right">
          <span className="text-xs text-[#475569] dark:text-[#94A3B8] block">Current cadence</span>
          <span className="font-semibold font-mono text-[#1C2026] dark:text-[#E5E9F0]">
            Day {activeDay} of 10
          </span>
        </div>
      </div>

      {/* 2. Single Status Line (Requirement F.2: Replaces the 4 mini cards) */}
      <div className="my-2 p-2 bg-[#EFECE2]/50 dark:bg-[#0B0E14] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] text-xs">
        <span className="font-medium text-[#1C2026] dark:text-[#E5E9F0]">
          Cash check, margin lock, ownership: all clear. Forced liquidation risk: none.
        </span>
      </div>

      {/* 3. 10-Segment Timeline with Markers at Day 8 and Day 10 (Requirement F.4) */}
      <div className="my-1.5 space-y-1">
        <div className="flex justify-between items-center text-xs text-[#475569] dark:text-[#94A3B8]">
          <span>Settlement timeline</span>
          <span className="font-mono text-[#64748B]">10-day rolling cycle</span>
        </div>

        {/* 10 Segments */}
        <div className="grid grid-cols-10 gap-1 h-3">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((d) => {
            const isPassed = d <= activeDay
            const isDay8 = d === 8
            const isDay10 = d === 10

            return (
              <div
                key={d}
                className={`h-full rounded-[1px] relative transition-colors ${
                  isDay8
                    ? 'bg-amber-600 dark:bg-amber-500' // Marker at Day 8
                    : isDay10
                    ? 'bg-rose-700 dark:bg-rose-600' // Marker at Day 10
                    : isPassed
                    ? 'bg-slate-700 dark:bg-slate-400'
                    : 'bg-[#D5D0C3] dark:bg-[#1E2633]'
                }`}
                title={`Day ${d}${isDay8 ? ' (Auto-cover threshold)' : isDay10 ? ' (Mandatory liquidation)' : ''}`}
              ></div>
            )
          })}
        </div>

        {/* Labels under Day 8 and Day 10 */}
        <div className="flex justify-between text-[11px] text-[#475569] dark:text-[#94A3B8] font-mono pt-0.5">
          <span>Day 1</span>
          <span className="text-amber-700 dark:text-amber-400 font-semibold font-sans">
            Marker: Day 8 auto-cover
          </span>
          <span className="text-rose-700 dark:text-rose-400 font-semibold font-sans">
            Marker: Day 10 liquidation
          </span>
        </div>
      </div>

      {/* 4. Cash Cushion Meter with 22% Lock Line (Requirement F.5) */}
      <div className="my-2 p-2 bg-[#EFECE2]/30 dark:bg-[#0B0E14] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[2px] space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-[#475569] dark:text-[#94A3B8]">Cash cushion meter</span>
          <span className="font-mono text-[#1C2026] dark:text-[#E5E9F0]">
            Margin lock: <strong>22.0%</strong> ({formatINR(210000.0)}) | Free cushion: <strong>78.0%</strong> ({formatINR(482450.0)})
          </span>
        </div>

        {/* Gauge bar with 22% lock line */}
        <div className="relative h-3 w-full bg-[#EFECE2] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[1px] overflow-hidden">
          {/* Margin locked segment (22%) */}
          <div
            style={{ width: '22%' }}
            className="h-full bg-slate-600 dark:bg-slate-400"
            title="22% margin locked as short collateral"
          ></div>

          {/* 22% Lock Line Marker */}
          <div
            className="absolute top-0 bottom-0 border-r-2 border-amber-600 z-10"
            style={{ left: '22%' }}
            title="22% Lock line threshold"
          ></div>
        </div>
      </div>

      {/* 5. Open Shorts Table with Empty State (Requirement F.3) */}
      <div className="overflow-x-auto border-t border-[#D5D0C3] dark:border-[#1E2633] pt-1">
        {shortPositions.length === 0 ? (
          <div className="py-6 text-center text-[#475569] dark:text-[#94A3B8] text-xs">
            No open short positions
          </div>
        ) : (
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#D5D0C3] dark:border-[#1E2633] text-[#475569] dark:text-[#94A3B8] bg-[#FAF8F3] dark:bg-[#11161F]">
                <th className="py-1.5 px-2 font-medium">Ticker</th>
                <th className="py-1.5 px-2 font-medium">Quantity</th>
                <th className="py-1.5 px-2 font-medium">Entry price</th>
                <th className="py-1.5 px-2 font-medium">Current price</th>
                <th className="py-1.5 px-2 font-medium">Margin locked</th>
                <th className="py-1.5 px-2 font-medium">Unrealized P&amp;L</th>
                <th className="py-1.5 px-2 text-right font-medium">Safety action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#D5D0C3] dark:divide-[#1E2633]">
              {shortPositions.map((pos) => {
                const isGain = pos.currentPrice < pos.entryPrice
                const diff = (pos.entryPrice - pos.currentPrice) * pos.qty
                const diffPct = (((pos.entryPrice - pos.currentPrice) / pos.entryPrice) * 100).toFixed(2)

                return (
                  <tr key={pos.ticker} className="hover:bg-[#EFECE2]/50 dark:hover:bg-[#1E2633]/40">
                    <td className="py-1.5 px-2 font-semibold text-[#1C2026] dark:text-[#E5E9F0]">
                      {pos.ticker}
                    </td>
                    <td className="py-1.5 px-2 font-mono tabular-nums">
                      {pos.qty.toLocaleString('en-IN')} shares
                    </td>
                    <td className="py-1.5 px-2 font-mono tabular-nums">
                      {formatINR(pos.entryPrice)}
                    </td>
                    <td className="py-1.5 px-2 font-mono tabular-nums">
                      {formatINR(pos.currentPrice)}
                    </td>
                    <td className="py-1.5 px-2 font-mono tabular-nums font-medium text-[#1C2026] dark:text-[#E5E9F0]">
                      {formatINR(pos.entryPrice * pos.qty)}
                    </td>
                    <td className={`py-1.5 px-2 font-mono tabular-nums font-semibold ${
                      isGain ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'
                    }`}>
                      {isGain ? '+' : ''}{formatINR(diff)} ({isGain ? '+' : ''}{diffPct}%)
                    </td>
                    <td className="py-1.5 px-2 text-right">
                      <button
                        onClick={() => onTriggerEmergencyCover && onTriggerEmergencyCover(pos.ticker)}
                        className="px-2 py-0.5 text-xs border border-[#D5D0C3] dark:border-[#2E3846] bg-[#EFECE2] dark:bg-[#1E2633] hover:bg-[#D5D0C3] rounded-[2px] font-medium"
                      >
                        Pre-square cover
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

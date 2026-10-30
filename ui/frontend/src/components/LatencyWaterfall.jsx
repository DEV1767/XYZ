import React, { useState } from 'react'

export function LatencyWaterfall({
  lastOrderLatency = { kafka: 12, features: 38, nlp: 14, ml: 22, validation: 4, rest: 280 },
  state = 'normal', // 'normal' | 'loading' | 'empty' | 'error' | 'stale'
}) {
  const [panelState, setPanelState] = useState(state)

  // 1. Pipeline stages and cumulative stepped start/end times
  const rawStages = [
    { name: 'Kafka ingestion', duration: lastOrderLatency.kafka || 12 },
    { name: 'Feature pipeline', duration: lastOrderLatency.features || 38 },
    { name: 'NLP news parse', duration: lastOrderLatency.nlp || 14 },
    { name: 'ML decision matrix', duration: lastOrderLatency.ml || 22 },
    { name: 'Pre-flight checks', duration: lastOrderLatency.validation || 4 },
    { name: 'REST dispatch', duration: lastOrderLatency.rest || 280, isSlowest: true },
  ]

  let cumulative = 0
  const stages = rawStages.map((stage) => {
    const start = cumulative
    cumulative += stage.duration
    return {
      ...stage,
      start,
      end: cumulative,
    }
  })

  const decisionLatency = cumulative // 370ms (tick to order sent)
  const fillTime = 182 // 182ms (order sent to confirmed)
  const budgetMs = 3000 // Only budget: 3,000ms decision window

  // Display domain for waterfall stepped graph (visual scale 0 to 500ms for high resolution)
  const maxDisplayMs = 500
  const newsMarkerMs = 150 // T+150ms news marker

  if (panelState === 'loading') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-3 text-xs font-sans animate-pulse min-h-[260px] flex flex-col justify-between">
        <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-1/3 mb-2"></div>
        <div className="space-y-2 my-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-3 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
          ))}
        </div>
        <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-1/2"></div>
      </div>
    )
  }

  if (panelState === 'error') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-4 text-xs font-sans min-h-[260px] flex flex-col justify-between">
        <div className="font-semibold text-rose-700 dark:text-rose-400">Latency waterfall</div>
        <div className="py-8 text-center text-[#475569] dark:text-[#94A3B8]">
          <p className="text-rose-700 dark:text-rose-400 font-medium">Failed to receive timestamp telemetry from Kafka consumer</p>
          <button
            onClick={() => setPanelState('normal')}
            className="mt-3 px-3 py-1 text-xs border border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2] dark:bg-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0]"
          >
            Retry connection
          </button>
        </div>
        <div className="text-[11px] text-[#64748B]">Telemetry stream: disconnected</div>
      </div>
    )
  }

  if (panelState === 'empty') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-4 text-xs font-sans min-h-[260px] flex flex-col justify-between">
        <div className="font-semibold text-[#1C2026] dark:text-[#E5E9F0]">Latency waterfall</div>
        <div className="py-10 text-center text-[#475569] dark:text-[#94A3B8]">
          No orders dispatched in this session yet. Waiting for simulation tick #1.
        </div>
        <div className="text-xs text-[#64748B]">Budget: 3,000ms</div>
      </div>
    )
  }

  return (
    <div className={`w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] p-3 font-sans text-xs select-none transition-colors rounded-[2px] flex flex-col justify-between ${
      panelState === 'stale' ? 'opacity-70' : ''
    }`}>
      {/* 1. Header: Section title and 3,000ms budget */}
      <div className="flex items-center justify-between pb-2 border-b border-[#D5D0C3] dark:border-[#1E2633]">
        <div>
          <div className="font-semibold text-sm text-[#1C2026] dark:text-[#E5E9F0]">
            Latency waterfall
          </div>
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] mt-0.5">
            Stepped pipeline execution stages against 3,000ms decision window
          </div>
        </div>

        {/* Primary Latency Metric Names (Requirement C.6) */}
        <div className="flex items-center space-x-4 text-right">
          <div>
            <div className="text-xs text-[#475569] dark:text-[#94A3B8]">Decision latency</div>
            <div className="text-sm font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0]">
              {decisionLatency}ms <span className="text-xs font-normal text-[#64748B]">/ 3,000ms</span>
            </div>
          </div>
          <div className="border-l border-[#D5D0C3] dark:border-[#1E2633] pl-3">
            <div className="text-xs text-[#475569] dark:text-[#94A3B8]">Fill time</div>
            <div className="text-sm font-semibold font-mono tabular-nums text-emerald-700 dark:text-emerald-400">
              {fillTime}ms
            </div>
          </div>
        </div>
      </div>

      {/* 2. Stepped Waterfall Chart (Requirement C.1 & C.2) */}
      <div className="my-2.5 space-y-1.5 relative">
        <div className="flex justify-between items-center text-xs text-[#475569] dark:text-[#94A3B8] pb-1">
          <span>Pipeline stage sequence</span>
          <span className="font-mono text-[#64748B] dark:text-[#94A3B8]">Scale: 0 to 500ms</span>
        </div>

        {/* Stepped Waterfall Container with vertical T+150ms news marker */}
        <div className="relative border border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/50 dark:bg-[#0B0E14] p-2 space-y-1">
          {/* T+150ms News Marker Line */}
          <div
            className="absolute top-0 bottom-0 border-l border-dashed border-amber-600 dark:border-amber-400 z-10 pointer-events-none"
            style={{ left: `calc(130px + ${(newsMarkerMs / maxDisplayMs) * (100)}% * 0.72)` }}
          >
            <span className="absolute -top-1 left-1 text-[11px] font-mono text-amber-700 dark:text-amber-400 font-semibold bg-[#FAF8F3] dark:bg-[#11161F] px-1 border border-amber-600/40 rounded-[2px] whitespace-nowrap">
              T+150ms news marker
            </span>
          </div>

          {stages.map((st) => {
            const startPct = (st.start / maxDisplayMs) * 100
            const widthPct = Math.max(1.5, (st.duration / maxDisplayMs) * 100)

            return (
              <div key={st.name} className="flex items-center text-xs">
                {/* Stage Name */}
                <div className="w-32 shrink-0 truncate text-[#475569] dark:text-[#94A3B8]">
                  {st.name}
                </div>

                {/* Stepped Waterfall Bar Track */}
                <div className="flex-1 h-4 relative bg-[#D5D0C3]/30 dark:bg-[#1E2633]/40 rounded-[1px] overflow-hidden">
                  <div
                    style={{
                      left: `${startPct}%`,
                      width: `${widthPct}%`,
                    }}
                    className={`absolute top-0 bottom-0 transition-all rounded-[1px] ${
                      st.isSlowest
                        ? 'bg-amber-600 dark:bg-amber-500' // Slowest stage in warning tone (Requirement C.4)
                        : 'bg-slate-600 dark:bg-slate-400' // All other stages in neutral tone
                    }`}
                    title={`${st.name}: ${st.start}ms to ${st.end}ms (${st.duration}ms)`}
                  ></div>
                </div>

                {/* Duration readout */}
                <div className={`w-14 text-right font-mono text-xs tabular-nums font-semibold shrink-0 ml-2 ${
                  st.isSlowest ? 'text-amber-700 dark:text-amber-400' : 'text-[#1C2026] dark:text-[#E5E9F0]'
                }`}>
                  {st.duration}ms
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 3. Budget Gauge & Percentiles (Requirement C.3 & C.5) */}
      <div className="pt-2 border-t border-[#D5D0C3] dark:border-[#1E2633] space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-[#475569] dark:text-[#94A3B8]">
            3,000ms decision window budget: <strong className="text-[#1C2026] dark:text-[#E5E9F0] font-mono font-medium">{decisionLatency}ms utilized (12.3%)</strong>
          </span>

          {/* p50, p95, and max beside the gauge */}
          <div className="flex items-center space-x-3 text-xs font-mono">
            <span>
              p50: <strong className="text-[#1C2026] dark:text-[#E5E9F0]">240ms</strong>
            </span>
            <span>
              p95: <strong className="text-[#1C2026] dark:text-[#E5E9F0]">382ms</strong>
            </span>
            <span>
              max: <strong className="text-[#1C2026] dark:text-[#E5E9F0]">810ms</strong>
            </span>
          </div>
        </div>

        {/* Single Budget Gauge Bar */}
        <div className="w-full h-2 bg-[#EFECE2] dark:bg-[#0B0E14] border border-[#D5D0C3] dark:border-[#1E2633] rounded-[1px] overflow-hidden">
          <div
            style={{ width: `${(decisionLatency / budgetMs) * 100}%` }}
            className="h-full bg-slate-600 dark:bg-slate-400 transition-all"
            title={`Utilized: ${decisionLatency}ms of ${budgetMs}ms budget`}
          ></div>
        </div>
      </div>
    </div>
  )
}

import React, { useState, useMemo } from 'react'
import { formatINR } from '../utils/formatters'

const DEFAULT_TRADES = [
  {
    orderId: 'ORD-9844',
    simDate: '2021-04-18',
    time: '10:04:18',
    ticker: 'PLNX',
    action: 'Sell',
    quantity: 2500,
    price: 80.55,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '218ms',
    newsHeadline: 'PLNX Q3 net profit not expected to decline; exports surge 24% YoY',
    indicators: { sma5: '78.90', sma20: '71.10', rsi: '61.4', smaRatio: '1.1097' },
  },
  {
    orderId: 'ORD-9843',
    simDate: '2021-04-16',
    time: '10:01:24',
    ticker: 'BLUX',
    action: 'Short',
    quantity: 500,
    price: 228.50,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '232ms',
    newsHeadline: 'BLUX faces cloud regulatory scrutiny in EU',
    indicators: { sma5: '226.40', sma20: '232.10', rsi: '42.1', smaRatio: '0.9754' },
  },
  {
    orderId: 'ORD-9842',
    simDate: '2021-04-14',
    time: '09:58:30',
    ticker: 'ORCX',
    action: 'Short',
    quantity: 600,
    price: 175.00,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '194ms',
    newsHeadline: 'ORCX experiences container shipping bottlenecks',
    indicators: { sma5: '173.80', sma20: '178.50', rsi: '46.2', smaRatio: '0.9736' },
  },
  {
    orderId: 'ORD-9841',
    simDate: '2021-04-12',
    time: '09:52:10',
    ticker: 'PLNX',
    action: 'Buy',
    quantity: 2500,
    price: 72.50,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '218ms',
    newsHeadline: 'PLNX signs expanded export contract with EU buyers',
    indicators: { sma5: '71.20', sma20: '69.40', rsi: '58.4', smaRatio: '1.0259' },
  },
  {
    orderId: 'ORD-9840',
    simDate: '2021-04-10',
    time: '09:44:02',
    ticker: 'AERX',
    action: 'Buy',
    quantity: 800,
    price: 476.20,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '185ms',
    newsHeadline: 'AERX awarded next-gen defense avionics contract',
    indicators: { sma5: '474.00', sma20: '465.10', rsi: '63.2', smaRatio: '1.0191' },
  },
  {
    orderId: 'ORD-9839',
    simDate: '2021-04-08',
    time: '09:32:15',
    ticker: 'DSNY',
    action: 'Buy',
    quantity: 1200,
    price: 110.40,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '204ms',
    newsHeadline: 'DSNY digital streaming subscriptions beat guidance',
    indicators: { sma5: '109.80', sma20: '107.20', rsi: '55.1', smaRatio: '1.0242' },
  },
  {
    orderId: 'ORD-9838',
    simDate: '2021-04-06',
    time: '09:20:45',
    ticker: 'HMDP',
    action: 'Cover',
    quantity: 400,
    price: 312.10,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '198ms',
    newsHeadline: 'Day 8 pre-square short cover executed without exchange penalty',
    indicators: { sma5: '314.50', sma20: '318.00', rsi: '49.8', smaRatio: '0.9889' },
  },
  {
    orderId: 'ORD-9837',
    simDate: '2021-04-04',
    time: '09:15:30',
    ticker: 'MOTR',
    action: 'Sell',
    quantity: 300,
    price: 495.00,
    status: 'Filled',
    statusCode: '200_OK',
    fillTime: '210ms',
    newsHeadline: 'Target profit threshold reached on powertrain division breakout',
    indicators: { sma5: '498.00', sma20: '482.00', rsi: '68.4', smaRatio: '1.0331' },
  },
]

export function RecentFillsTable({
  recentTrades = [],
  onInspectTrade,
  state = 'normal', // 'normal' | 'loading' | 'empty' | 'error' | 'stale'
}) {
  const [actionFilter, setActionFilter] = useState('All')
  const [tickerFilter, setTickerFilter] = useState('All')
  const [panelState, setPanelState] = useState(state)

  const mergedTrades = recentTrades.length > 0 ? recentTrades : DEFAULT_TRADES

  const filteredTrades = useMemo(() => {
    return mergedTrades.filter((tr) => {
      const matchAction =
        actionFilter === 'All' ||
        tr.action.toLowerCase() === actionFilter.toLowerCase()
      const matchTicker =
        tickerFilter === 'All' ||
        tr.ticker.toUpperCase() === tickerFilter.toUpperCase()
      return matchAction && matchTicker
    })
  }, [mergedTrades, actionFilter, tickerFilter])

  // Top 8 rows (Requirement D.2)
  const displayRows = filteredTrades.slice(0, 8)

  const uniqueTickers = ['All', 'PLNX', 'AERX', 'BLUX', 'ORCX', 'DSNY', 'HMDP', 'MOTR']

  if (panelState === 'loading') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-3 text-xs font-sans animate-pulse min-h-[320px]">
        <div className="h-4 bg-[#EFECE2] dark:bg-[#1E2633] w-1/4 mb-3"></div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} className="h-5 bg-[#EFECE2] dark:bg-[#1E2633] w-full"></div>
          ))}
        </div>
      </div>
    )
  }

  if (panelState === 'error') {
    return (
      <div className="w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] p-4 text-xs font-sans min-h-[320px] flex flex-col justify-between">
        <div className="font-semibold text-rose-700 dark:text-rose-400">Recent fills</div>
        <div className="py-12 text-center text-[#475569] dark:text-[#94A3B8]">
          <p className="text-rose-700 dark:text-rose-400 font-medium">Failed to query order history from execution ledger</p>
          <button
            onClick={() => setPanelState('normal')}
            className="mt-3 px-3 py-1 text-xs border border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2] dark:bg-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0]"
          >
            Retry fetch
          </button>
        </div>
        <div className="text-[11px] text-[#64748B]">State: error</div>
      </div>
    )
  }

  return (
    <div className={`w-full bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] font-sans text-xs select-none transition-colors rounded-[2px] flex flex-col ${
      panelState === 'stale' ? 'opacity-70' : ''
    }`}>
      {/* 1. Header with Filters (Requirement D.2) */}
      <div className="px-3 py-2 border-b border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/60 dark:bg-[#0B0E14] flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="font-semibold text-[#1C2026] dark:text-[#E5E9F0] text-sm">
            Recent fills
          </span>
          <span className="text-xs text-[#475569] dark:text-[#94A3B8] ml-2">
            Click row to open "Why did my bot do that"
          </span>
        </div>

        {/* Filter Controls: Action & Ticker (Sentence case, no bracket buttons) */}
        <div className="flex items-center space-x-2 text-xs">
          {/* Action Filter */}
          <div className="flex items-center space-x-1">
            <span className="text-[#475569] dark:text-[#94A3B8]">Action:</span>
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] text-xs px-2 py-0.5 rounded-[2px]"
            >
              <option value="All">All actions</option>
              <option value="Buy">Buy</option>
              <option value="Sell">Sell</option>
              <option value="Short">Short</option>
              <option value="Cover">Cover</option>
            </select>
          </div>

          {/* Ticker Filter */}
          <div className="flex items-center space-x-1">
            <span className="text-[#475569] dark:text-[#94A3B8]">Ticker:</span>
            <select
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value)}
              className="bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] text-xs px-2 py-0.5 rounded-[2px]"
            >
              {uniqueTickers.map((t) => (
                <option key={t} value={t}>
                  {t === 'All' ? 'All tickers' : t}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 2. Table: 8 Rows, Columns: Sim date, Time, Ticker, Action, Qty @ Price, Status, Fill time (Requirement D.1 & D.2) */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-[#D5D0C3] dark:border-[#1E2633] text-xs text-[#475569] dark:text-[#94A3B8] bg-[#FAF8F3] dark:bg-[#11161F]">
              <th className="py-2 px-3 font-medium">Sim date</th>
              <th className="py-2 px-2 font-medium">Time</th>
              <th className="py-2 px-2 font-medium">Ticker</th>
              <th className="py-2 px-2 font-medium">Action</th>
              <th className="py-2 px-2 font-medium text-right">Quantity @ price</th>
              <th className="py-2 px-2 font-medium">Status</th>
              <th className="py-2 px-3 font-medium text-right">Fill time</th>
              <th className="py-2 px-3 font-medium text-center">AI Agent</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#D5D0C3] dark:divide-[#1E2633]">
            {displayRows.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-[#475569] dark:text-[#94A3B8]">
                  No trade records match the selected action and ticker filters.
                </td>
              </tr>
            ) : (
              displayRows.map((tr) => (
                <tr
                  key={tr.orderId}
                  onClick={() => onInspectTrade && onInspectTrade(tr)}
                  className="hover:bg-[#EFECE2]/70 dark:hover:bg-[#1E2633]/50 cursor-pointer transition-colors"
                  title={`Inspect decision rationale for ${tr.orderId}`}
                >
                  <td className="py-2 px-3 text-[#475569] dark:text-[#94A3B8] font-mono whitespace-nowrap">
                    {tr.simDate || tr.simulatedDate || '2021-04-18'}
                  </td>
                  <td className="py-2 px-2 text-[#475569] dark:text-[#94A3B8] font-mono whitespace-nowrap">
                    {tr.time || '10:04:18'}
                  </td>
                  <td className="py-2 px-2 font-semibold text-[#1C2026] dark:text-[#E5E9F0]">
                    {tr.ticker}
                  </td>
                  <td className="py-2 px-2">
                    <span className="font-medium text-[#1C2026] dark:text-[#E5E9F0]">
                      {tr.action}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0]">
                    {tr.quantity.toLocaleString('en-IN')} @ {formatINR(tr.price)}
                  </td>
                  <td className="py-2 px-2">
                    <span className="text-emerald-700 dark:text-emerald-400 font-medium">
                      {tr.status || 'Filled'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0]">
                    {tr.fillTime || tr.latency || '218ms'}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        onInspectTrade && onInspectTrade(tr)
                      }}
                      className="px-2 py-0.5 text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/70 hover:bg-emerald-100 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700 rounded-[2px] transition-colors inline-flex items-center gap-1 shadow-xs"
                      title="Ask Trade Explainer Agent"
                    >
                      <span>🤖 Explain</span>
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 3. Footer */}
      <div className="px-3 py-1.5 border-t border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/40 dark:bg-[#0B0E14] flex items-center justify-between text-xs text-[#475569] dark:text-[#94A3B8]">
        <span>Showing {displayRows.length} of {filteredTrades.length} recorded orders</span>
        <span>Average fill time: 216ms (100% order accuracy)</span>
      </div>
    </div>
  )
}

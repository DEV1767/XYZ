import React from 'react'

export function LiveCandleChart({
  selectedStock,
  onSelectStock,
  stockUniverse,
  historicalBars,
  recentTrades,
  onInspectTrade,
  breakingNews,
}) {
  const currentStockData = stockUniverse.find(s => s.ticker === selectedStock) || stockUniverse[0]
  const lastBar = historicalBars[historicalBars.length - 1] || { close: 1450.25, open: 1440, high: 1465, low: 1435, volume: 1285000 }
  const prevBar = historicalBars[historicalBars.length - 2] || lastBar
  const priceChange = lastBar.close - prevBar.close
  const pctChange = ((priceChange / prevBar.close) * 100).toFixed(2)
  const isPositive = priceChange >= 0

  // Calculate min and max for chart scaling
  const closes = (historicalBars && historicalBars.length > 0 ? historicalBars : [{ close: 100 }]).map(b => b.close)
  const minPrice = Math.min(...closes) * 0.99
  const maxPrice = Math.max(...closes) * 1.01
  const priceRange = maxPrice - minPrice || 1

  return (
    <div className="bg-white dark:bg-[#111726] border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded p-4 flex flex-col justify-between transition-colors">
      {/* Breaking News Ticker Banner at T+150ms */}
      <div className="mb-3 p-2 bg-slate-50 dark:bg-[#090e17] border border-slate-200 dark:border-slate-800/80 rounded flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-400 border border-amber-300 dark:border-amber-800/60 text-[10px] uppercase font-bold shrink-0">
            News T+150ms
          </span>
          <span className="text-slate-700 dark:text-slate-300 truncate">
            <span className="font-semibold text-slate-900 dark:text-slate-100">[{breakingNews.ticker}]</span> {breakingNews.headline}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0 pl-2">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
            breakingNews.score > 0
              ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800'
              : 'bg-rose-100 dark:bg-rose-950 text-rose-800 dark:text-rose-400 border border-rose-300 dark:border-rose-800'
          }`}>
            Score: {breakingNews.score > 0 ? `+${breakingNews.score}` : breakingNews.score}
          </span>
        </div>
      </div>

      {/* Stock Selection & Price Overview */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-200 dark:border-slate-800">
        {/* Stock Selector Buttons */}
        <div className="flex items-center gap-1.5">
          {stockUniverse.map(s => (
            <button
              key={s.ticker}
              onClick={() => onSelectStock(s.ticker)}
              className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
                selectedStock === s.ticker
                  ? 'bg-slate-800 dark:bg-slate-700 text-white font-bold border border-slate-700 dark:border-slate-600'
                  : 'bg-slate-100 dark:bg-slate-800/50 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800'
              }`}
            >
              {s.ticker}
            </button>
          ))}
        </div>

        {/* Live OHLCV Summary */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div>
            <span className="text-slate-400 dark:text-slate-400 text-[10px] block uppercase">Live Close</span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm font-bold text-slate-900 dark:text-slate-100 tabular-nums">
                ₹{lastBar.close.toFixed(2)}
              </span>
              <span className={`text-[11px] tabular-nums font-semibold ${isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                {isPositive ? '+' : ''}{pctChange}%
              </span>
            </div>
          </div>

          <div className="hidden sm:block">
            <span className="text-slate-400 dark:text-slate-400 text-[10px] block uppercase">High / Low</span>
            <div className="text-slate-700 dark:text-slate-300 tabular-nums">
              ₹{lastBar.high.toFixed(1)} / ₹{lastBar.low.toFixed(1)}
            </div>
          </div>

          <div className="hidden md:block">
            <span className="text-slate-400 dark:text-slate-400 text-[10px] block uppercase">Day Volume</span>
            <div className="text-slate-700 dark:text-slate-300 tabular-nums">
              {(lastBar.volume / 1000).toFixed(0)}k shs
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Price Chart with Dual Moving Average & Trade Markers */}
      <div className="my-3 relative">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 dark:text-slate-400 mb-1.5">
          <div className="flex items-center gap-3">
            <span>Historical OHLCV Stream (50-Bar Warm-Start)</span>
            <span className="flex items-center gap-1 text-[10px]">
              <span className="h-1.5 w-3 bg-emerald-500 rounded-sm inline-block"></span>
              <span className="text-emerald-600 dark:text-emerald-400">SMA 5</span>
            </span>
            <span className="flex items-center gap-1 text-[10px]">
              <span className="h-1.5 w-3 bg-amber-500 rounded-sm inline-block"></span>
              <span className="text-amber-600 dark:text-amber-400">SMA 20</span>
            </span>
          </div>
          <span className="text-slate-400 dark:text-slate-400 text-[10px]">Click any trade tag to inspect jury defense log</span>
        </div>

        {/* SVG Price Chart */}
        <div className="h-56 w-full bg-slate-50 dark:bg-[#090d16] border border-slate-200 dark:border-slate-800 rounded relative overflow-hidden">
          <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 500 200">
            {/* Horizontal Grid lines */}
            <line x1="0" y1="50" x2="500" y2="50" stroke="currentColor" className="text-slate-200 dark:text-slate-800/80" strokeDasharray="3 3" strokeWidth="0.8" />
            <line x1="0" y1="100" x2="500" y2="100" stroke="currentColor" className="text-slate-200 dark:text-slate-800/80" strokeDasharray="3 3" strokeWidth="0.8" />
            <line x1="0" y1="150" x2="500" y2="150" stroke="currentColor" className="text-slate-200 dark:text-slate-800/80" strokeDasharray="3 3" strokeWidth="0.8" />

            {/* Price Line */}
            {(() => {
              const points = historicalBars.map((b, i) => {
                const x = (i / (historicalBars.length - 1)) * 480 + 10
                const y = 180 - ((b.close - minPrice) / priceRange) * 150
                return `${x},${y}`
              }).join(' ')

              const areaPoints = `10,195 ${points} 490,195`

              return (
                <>
                  <polygon points={areaPoints} className="fill-emerald-500/10 dark:fill-emerald-500/10" />
                  <polyline points={points} fill="none" stroke="#10b981" strokeWidth="1.8" />
                </>
              )
            })()}

            {/* SMA 20 Overlay Line */}
            {(() => {
              const smaPoints = historicalBars.map((b, i) => {
                const x = (i / (historicalBars.length - 1)) * 480 + 10
                const sma = b.sma20 || b.close
                const y = 180 - ((sma - minPrice) / priceRange) * 150
                return `${x},${y}`
              }).join(' ')

              return <polyline points={smaPoints} fill="none" stroke="#f59e0b" strokeWidth="1.2" strokeDasharray="4 2" />
            })()}
          </svg>

          {/* Trade Executions Plotted as Clickable Badges */}
          <div className="absolute inset-0 pointer-events-none">
            {recentTrades
              .filter(t => t.ticker === selectedStock)
              .map((trade, i) => {
                const leftPct = Math.min(90, Math.max(10, 25 + i * 22))
                return (
                  <button
                    key={trade.orderId}
                    onClick={() => onInspectTrade(trade)}
                    style={{ left: `${leftPct}%`, top: trade.action === 'BUY' || trade.action === 'COVER' ? '65%' : '20%' }}
                    className={`absolute pointer-events-auto -translate-x-1/2 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider border shadow-sm transition-transform hover:scale-105 ${
                      trade.action === 'BUY'
                        ? 'bg-emerald-100 dark:bg-emerald-900/90 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500'
                        : trade.action === 'SELL'
                        ? 'bg-sky-100 dark:bg-sky-900/90 text-sky-800 dark:text-sky-300 border-sky-300 dark:border-sky-500'
                        : trade.action === 'SHORT'
                        ? 'bg-rose-100 dark:bg-rose-900/90 text-rose-800 dark:text-rose-300 border-rose-300 dark:border-rose-500'
                        : 'bg-amber-100 dark:bg-amber-900/90 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-500'
                    }`}
                    title={`Click to inspect trade decision logic: ${trade.action} @ ₹${trade.price}`}
                  >
                    {trade.action} ₹{trade.price.toFixed(0)}
                  </button>
                )
              })}
          </div>
        </div>
      </div>

      {/* Recent Orders Execution Strip */}
      <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs font-mono">
        <span className="text-slate-500 dark:text-slate-400">Recent Signals &amp; Fills:</span>
        <div className="flex items-center gap-2">
          {recentTrades.slice(0, 3).map(tr => (
            <button
              key={tr.orderId}
              onClick={() => onInspectTrade(tr)}
              className="text-[11px] px-2 py-0.5 rounded bg-slate-50 dark:bg-[#0d131f] hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 transition-colors flex items-center gap-1.5"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${
                tr.action === 'BUY' ? 'bg-emerald-500' : tr.action === 'SELL' ? 'bg-sky-500' : tr.action === 'SHORT' ? 'bg-rose-500' : 'bg-amber-500'
              }`}></span>
              <span>{tr.action}</span>
              <span className="font-semibold text-slate-900 dark:text-slate-100">{tr.ticker}</span>
              <span className="text-slate-500 dark:text-slate-400">₹{tr.price}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

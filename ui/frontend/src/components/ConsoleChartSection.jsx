import React, { useState, useMemo, useRef, useEffect } from 'react'
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
import { formatINR } from '../utils/formatters'

const STOCK_METRICS_FALLBACK = {
  PLNX: { close: 162.25, changePct: '+11.78%', high: 209.05, low: 87.39, volume: '281.2M', volRatio: '2.64x SMA20', smaRatio: '1.1213 (Golden cross)', rsi: '61.4', min: 80, max: 215 },
  AERX: { close: 489.02, changePct: '+4.12%', high: 494.50, low: 472.00, volume: '142.8M', volRatio: '1.82x SMA20', smaRatio: '1.0420 (Bullish trend)', rsi: '57.8', min: 450, max: 650 },
  BLUX: { close: 251.46, changePct: '-1.45%', high: 258.20, low: 247.00, volume: '98.4M', volRatio: '1.18x SMA20', smaRatio: '0.9650 (Neutral)', rsi: '48.1', min: 210, max: 280 },
  ORCX: { close: 169.66, changePct: '-1.85%', high: 174.50, low: 168.20, volume: '64.2M', volRatio: '0.94x SMA20', smaRatio: '0.9810 (Bearish trend)', rsi: '46.2', min: 155, max: 190 },
  ROUT: { close: 70.35, changePct: '+1.20%', high: 72.80, low: 69.40, volume: '115.0M', volRatio: '1.05x SMA20', smaRatio: '1.0110 (Neutral)', rsi: '51.4', min: 55, max: 115 },
  DSNY: { close: 112.03, changePct: '+2.60%', high: 114.20, low: 109.10, volume: '88.6M', volRatio: '1.32x SMA20', smaRatio: '1.0250 (Bullish trend)', rsi: '54.9', min: 90, max: 135 },
  HAVN: { close: 172.01, changePct: '+0.85%', high: 176.50, low: 170.20, volume: '42.1M', volRatio: '0.88x SMA20', smaRatio: '1.0080 (Neutral)', rsi: '50.2', min: 110, max: 195 },
  HMDP: { close: 315.40, changePct: '+3.10%', high: 318.00, low: 306.50, volume: '76.3M', volRatio: '1.45x SMA20', smaRatio: '1.0310 (Bullish trend)', rsi: '59.1', min: 285, max: 350 },
  MOTR: { close: 82.50, changePct: '+1.40%', high: 86.50, low: 78.00, volume: '190.5M', volRatio: '2.10x SMA20', smaRatio: '1.0850 (Strong bull)', rsi: '64.8', min: 50, max: 120 },
  SONA: { close: 527.45, changePct: '+1.68%', high: 585.00, low: 515.00, volume: '95.4M', volRatio: '1.44x SMA20', smaRatio: '1.0536 (Bullish)', rsi: '68.0', min: 380, max: 590 },
}

export function ConsoleChartSection({
  selectedStock,
  onSelectStock,
  stockUniverse,
  recentTrades,
  onInspectTrade,
  breakingNews,
}) {
  const [viewScope, setViewScope] = useState(90) // default 90 days for clear buy/sell dips (or 'today', 45, 0)
  const [chartMode, setChartMode] = useState('candles') // 'candles' | 'line'
  const [showDips, setShowDips] = useState(true) // Dip visualizer toggle
  const [hoverIndex, setHoverIndex] = useState(null)
  const [cursorPos, setCursorPos] = useState({ x: 0, y: 0 })
  const [chartPayload, setChartPayload] = useState({ mode: 'daily', ticks: [], bars: [], orders: [] })
  const [selectedOrderPopup, setSelectedOrderPopup] = useState(null)
  const [lastTickPulse, setLastTickPulse] = useState(false)
  const svgRef = useRef(null)

  const isTodayMode = viewScope === 'today'

  // Fetch real simulation data with dates, days, intraday ticks, and executed orders
  useEffect(() => {
    let isMounted = true
    const fetchChartData = async () => {
      try {
        const url = isTodayMode
          ? `${API_BASE}/api/chart-data?ticker=${selectedStock}&mode=today&limit=120`
          : `${API_BASE}/api/chart-data?ticker=${selectedStock}&mode=daily&limit=${viewScope}`

        const res = await fetch(url)
        if (res.ok) {
          const data = await res.json()
          if (isMounted && data) {
            setChartPayload(data)
            setLastTickPulse(true)
            setTimeout(() => setLastTickPulse(false), 800)
          }
        }
      } catch {
        // Keep existing data on transient network hiccups
      }
    }

    fetchChartData()
    const intervalTime = isTodayMode ? 2000 : 5000
    const interval = setInterval(fetchChartData, intervalTime)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [selectedStock, viewScope, isTodayMode])

  const defaultMetrics = STOCK_METRICS_FALLBACK[selectedStock] || STOCK_METRICS_FALLBACK.PLNX

  // Build unified historical or intraday series
  const activeBars = useMemo(() => {
    if (isTodayMode) {
      // Intraday Today Ticks Stream
      const rawTicks = chartPayload.ticks || []
      if (rawTicks.length > 0) {
        return rawTicks.map((t, i) => {
          const prevClose = i > 0 ? rawTicks[i - 1].close : t.open
          const isUp = t.close >= prevClose
          const volMil = t.volume > 100000 ? +(t.volume / 1000000).toFixed(1) : +(t.volume || 10).toFixed(1)
          return {
            index: i + 1,
            time: t.time || '09:15:00',
            timestamp: t.timestamp || '',
            display_label: t.time || `Tick #${i + 1}`,
            open: t.open,
            high: t.high,
            low: t.low,
            close: t.close,
            volume: volMil,
            raw_volume: t.volume,
            isUp,
            orders: Array.isArray(t.orders) ? t.orders : [],
          }
        })
      }
    } else {
      // Multi-Day Daily Candles
      const rawBars = chartPayload.bars || []
      if (rawBars.length > 0) {
        const list = rawBars.map((b, i) => {
          const prevClose = i > 0 ? rawBars[i - 1].close : b.open
          const isUp = b.close >= prevClose
          const volMil = b.volume > 100000 ? +(b.volume / 1000000).toFixed(1) : +(b.volume || 10).toFixed(1)
          return {
            index: i + 1,
            day: b.day || (i + 1),
            date: b.date || '',
            display_date: b.display_date || b.date || '',
            short_date: b.short_date || (b.date ? b.date.slice(5) : `Day ${i + 1}`),
            display_label: `Day ${b.day || (i + 1)} • ${b.short_date || ''}`,
            open: b.open,
            high: b.high,
            low: b.low,
            close: b.close,
            volume: volMil,
            raw_volume: b.volume,
            isUp,
            orders: Array.isArray(b.orders) ? b.orders : [],
          }
        })

        // Compute SMA5, SMA20 and Wilder RSI (14)
        for (let i = 0; i < list.length; i++) {
          const slice5 = list.slice(Math.max(0, i - 4), i + 1)
          list[i].sma5 = slice5.reduce((acc, b) => acc + b.close, 0) / slice5.length

          const slice20 = list.slice(Math.max(0, i - 19), i + 1)
          list[i].sma20 = slice20.reduce((acc, b) => acc + b.close, 0) / slice20.length

          if (i >= 14) {
            let gains = 0, losses = 0
            for (let j = i - 13; j <= i; j++) {
              const diff = list[j].close - list[j - 1].close
              if (diff >= 0) gains += diff
              else losses += Math.abs(diff)
            }
            const rs = losses === 0 ? 100 : gains / losses
            list[i].rsi = (100 - (100 / (1 + rs))).toFixed(1)
          } else {
            list[i].rsi = (50 + (list[i].close >= list[i].sma5 ? 5.8 : -4.8)).toFixed(1)
          }
        }
        return list
      }
    }

    // Fallback if data loading
    const count = 50
    const fallback = []
    const range = defaultMetrics.max - defaultMetrics.min
    let p = defaultMetrics.min + range * 0.4
    for (let i = 0; i < count; i++) {
      p = Math.max(defaultMetrics.min, Math.min(defaultMetrics.max, p + (Math.sin(i * 0.3) * (range * 0.05))))
      fallback.push({
        index: i + 1,
        time: `07:${String(i).padStart(2, '0')}:00`,
        day: i + 1,
        date: `2026-10-30`,
        display_label: isTodayMode ? `07:${String(i).padStart(2, '0')}:00` : `Day ${i + 1}`,
        open: p - 1.5,
        high: p + 3.0,
        low: p - 2.5,
        close: p,
        volume: 85 + (i * 2),
        isUp: i % 2 === 0,
        sma5: p,
        sma20: p * 0.98,
        rsi: '55.0',
        orders: [],
      })
    }
    return fallback
  }, [chartPayload, isTodayMode, defaultMetrics])

  // Chart dimensions
  const barsCount = activeBars.length || 1
  const svgWidth = 840
  const svgHeight = 330
  const leftX = 30
  const rightX = 745
  const plotWidth = rightX - leftX

  const priceTopY = 24
  const priceBottomY = 205
  const priceHeight = priceBottomY - priceTopY

  const volTopY = 240
  const volBottomY = 295
  const volHeight = volBottomY - volTopY

  // Price bounds: Tightened so dips plunge steeply down the screen
  const allPrices = useMemo(() => {
    const list = []
    activeBars.forEach((b) => {
      list.push(b.high, b.low, b.close, b.open)
      if (b.orders) {
        b.orders.forEach((o) => list.push(o.price))
      }
    })
    return list.length ? list : [defaultMetrics.close]
  }, [activeBars, defaultMetrics])

  const minP = Math.min(...allPrices) * 0.985
  const maxP = Math.max(...allPrices) * 1.015
  const pRange = maxP - minP || 1

  const maxVol = Math.max(10, ...activeBars.map((b) => (typeof b.volume === 'number' ? b.volume : 50)))

  const getX = (index) => leftX + (index / Math.max(1, barsCount - 1)) * plotWidth
  const getY = (val) => priceBottomY - ((val - minP) / pRange) * priceHeight
  const getVolY = (vol) => volBottomY - (Math.min(vol, maxVol) / maxVol) * volHeight

  // Mouse hover tracking
  const handleMouseMove = (e) => {
    if (!svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const rawX = e.clientX - rect.left
    const rawY = e.clientY - rect.top
    const scaleX = svgWidth / rect.width
    const scaleY = svgHeight / rect.height
    const x = Math.max(leftX, Math.min(rightX, rawX * scaleX))
    const y = Math.max(priceTopY, Math.min(volBottomY, rawY * scaleY))

    const ratio = (x - leftX) / plotWidth
    const idx = Math.min(barsCount - 1, Math.max(0, Math.round(ratio * (barsCount - 1))))
    setHoverIndex(idx)
    setCursorPos({ x, y })
  }

  const handleMouseLeave = () => {
    setHoverIndex(null)
  }

  // Active bar metrics readout
  const activeBar = (hoverIndex !== null && activeBars[hoverIndex])
    ? activeBars[hoverIndex]
    : (activeBars[barsCount - 1] || defaultMetrics)
  const prevBar = (hoverIndex !== null && hoverIndex > 0 && activeBars[hoverIndex - 1])
    ? activeBars[hoverIndex - 1]
    : (activeBars[Math.max(0, barsCount - 2)] || activeBar)
  const activeChange = (activeBar.close || 0) - (prevBar.close || 0)
  const activeChangePct = prevBar && prevBar.close ? ((activeChange / prevBar.close) * 100).toFixed(2) : '0.00'

  // Polylines
  const closePoints = activeBars.map((b, i) => `${getX(i).toFixed(1)},${getY(b.close).toFixed(1)}`).join(' ')
  const sma5Points = activeBars.map((b, i) => b.sma5 ? `${getX(i).toFixed(1)},${getY(b.sma5).toFixed(1)}` : '').filter(Boolean).join(' ')
  const sma20Points = activeBars.map((b, i) => b.sma20 ? `${getX(i).toFixed(1)},${getY(b.sma20).toFixed(1)}` : '').filter(Boolean).join(' ')

  // Live Area Polygon under curve for Today's Live Graph
  const liveAreaPoints = useMemo(() => {
    if (!isTodayMode || activeBars.length < 2) return ''
    const firstX = getX(0).toFixed(1)
    const lastX = getX(barsCount - 1).toFixed(1)
    return `${closePoints} ${lastX},${priceBottomY} ${firstX},${priceBottomY}`
  }, [isTodayMode, activeBars, closePoints, barsCount])

  // Extract all executed BUYs and SELLs
  const executionMarkers = useMemo(() => {
    const list = []
    activeBars.forEach((b, idx) => {
      if (b.orders && b.orders.length > 0) {
        b.orders.forEach((ord) => {
          list.push({
            barIndex: idx,
            time: b.time || ord.time || '',
            day: b.day,
            date: b.date || '',
            display_label: isTodayMode ? (b.time || ord.time) : (b.display_date || `Day ${b.day}`),
            action: ord.action,
            quantity: ord.quantity,
            price: ord.price,
            order_cost: ord.order_cost,
            reason: ord.reason,
            order_id: ord.order_id,
            x: getX(idx),
            y: getY(ord.price),
          })
        })
      }
    })
    return list
  }, [activeBars, isTodayMode, minP, pRange, plotWidth, leftX, barsCount])

  // Dynamic Trade Cycles & Dip/Drawdown Calculator
  const tradeCycles = useMemo(() => {
    const cycles = []
    let currentBuy = null

    activeBars.forEach((bar, idx) => {
      if (bar.orders && bar.orders.length > 0) {
        bar.orders.forEach((ord) => {
          if (ord.action === 'BUY') {
            currentBuy = {
              buyIdx: idx,
              bar,
              order: ord,
              price: ord.price,
              x: getX(idx),
              y: getY(ord.price),
              label: `▲ BOUGHT ${ord.quantity} @ ${formatINR(ord.price, 0)}`,
            }
          } else if (ord.action === 'SELL' && currentBuy) {
            const sellIdx = idx
            const sellPrice = ord.price
            const sellX = getX(sellIdx)
            const sellY = getY(sellPrice)

            const slice = activeBars.slice(currentBuy.buyIdx, sellIdx + 1)
            let troughPrice = currentBuy.price
            let troughIdx = currentBuy.buyIdx

            slice.forEach((b, sIdx) => {
              const pLow = b.low !== undefined ? b.low : b.close
              if (pLow < troughPrice) {
                troughPrice = pLow
                troughIdx = currentBuy.buyIdx + sIdx
              }
            })

            const dipPct = ((troughPrice - currentBuy.price) / currentBuy.price) * 100
            const pnlPct = ((sellPrice - currentBuy.price) / currentBuy.price) * 100
            const isDip = dipPct < -0.5 || pnlPct < 0

            const baselineY = getY(currentBuy.price)
            const curve = slice.map((b, sIdx) => `${getX(currentBuy.buyIdx + sIdx).toFixed(1)},${getY(b.close).toFixed(1)}`).join(' ')
            const polygonPoints = `${curve} ${sellX.toFixed(1)},${baselineY.toFixed(1)} ${currentBuy.x.toFixed(1)},${baselineY.toFixed(1)}`

            cycles.push({
              id: `${currentBuy.order.order_id || currentBuy.buyIdx}-${ord.order_id || sellIdx}`,
              buy: currentBuy,
              sell: {
                sellIdx,
                bar,
                order: ord,
                price: sellPrice,
                x: sellX,
                y: sellY,
                label: `▼ SOLD ${ord.quantity} @ ${formatINR(sellPrice, 0)}`,
              },
              trough: {
                price: troughPrice,
                idx: troughIdx,
                x: getX(troughIdx),
                y: getY(troughPrice),
                dipPct,
              },
              dipPct,
              pnlPct,
              isDip,
              polygonPoints,
              baselineY,
            })
            currentBuy = null
          }
        })
      }
    })
    return cycles
  }, [activeBars, minP, pRange, plotWidth, leftX, barsCount])

  // Calculate worst dip in visible range
  const worstDipInView = useMemo(() => {
    if (!tradeCycles.length) return null
    return tradeCycles.reduce((min, c) => (c.dipPct < min.dipPct ? c : min), tradeCycles[0])
  }, [tradeCycles])

  const totalBuysCount = executionMarkers.filter((m) => m.action === 'BUY').length
  const totalSellsCount = executionMarkers.filter((m) => m.action === 'SELL').length

  // X-Axis Markers: Intraday Time (Today) or Simulation Day/Date (Historical)
  const xAxisMarkers = useMemo(() => {
    if (barsCount < 2) return []
    const step = Math.max(1, Math.floor((barsCount - 1) / 4))
    const indices = [0, step, step * 2, step * 3, barsCount - 1]
    return indices.map((idx) => {
      const b = activeBars[idx]
      return {
        idx,
        x: getX(idx),
        labelTop: isTodayMode ? (b?.time || '') : `Day ${b?.day || idx + 1}`,
        labelBottom: isTodayMode ? 'Live' : (b?.short_date || ''),
      }
    })
  }, [barsCount, activeBars, isTodayMode, leftX, plotWidth])

  // Last bar coordinate for live pulsing radar dot
  const lastBarX = getX(barsCount - 1)
  const lastBarY = getY(activeBars[barsCount - 1]?.close || defaultMetrics.close)

  // Price grid levels
  const pLevels = [
    maxP,
    minP + pRange * 0.75,
    minP + pRange * 0.50,
    minP + pRange * 0.25,
    minP,
  ]

  const hoveredPrice = maxP - ((cursorPos.y - priceTopY) / priceHeight) * pRange
  const sessionMetrics = chartPayload.session_metrics || {}

  return (
    <div className="w-full flex flex-col bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] select-none transition-colors rounded-[2px] font-sans shadow-sm">
      {/* 1. Connected Stock Tab Strip */}
      <div className="flex items-center overflow-x-auto scrollbar-none border-b border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/60 dark:bg-[#0B0E14] text-xs">
        {stockUniverse.map((s) => {
          const isActive = selectedStock === s.ticker
          return (
            <button
              key={s.ticker}
              onClick={() => {
                onSelectStock(s.ticker)
                setSelectedOrderPopup(null)
              }}
              className={`px-3.5 py-2 font-medium transition-colors border-r border-[#D5D0C3] dark:border-[#1E2633] rounded-none shrink-0 ${
                isActive
                  ? 'bg-[#FAF8F3] dark:bg-[#11161F] text-[#1C2026] dark:text-[#E5E9F0] border-b-2 border-b-emerald-600 dark:border-b-emerald-400 font-bold'
                  : 'text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026] dark:hover:text-[#E5E9F0]'
              }`}
            >
              {s.ticker}
            </button>
          )
        })}
      </div>

      {/* 2. Top 5-Column Mini-Grid Readout with Real Dips & Drawdown */}
      <div className="grid grid-cols-2 sm:grid-cols-5 border-b border-[#D5D0C3] dark:border-[#1E2633] text-xs divide-x divide-[#D5D0C3] dark:divide-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F]">
        {/* Metric 1: Close / LTP + Timeline Position */}
        <div className="p-2.5">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] flex items-center justify-between">
            <span className="font-medium">{isTodayMode ? 'Live LTP' : 'Close price'}</span>
            <span className="font-mono text-emerald-700 dark:text-emerald-400 font-semibold flex items-center space-x-1">
              {isTodayMode && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>}
              <span>{isTodayMode ? activeBar.time : `Day ${activeBar.day} • ${activeBar.short_date}`}</span>
            </span>
          </div>
          <div className="text-base font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] mt-0.5">
            {formatINR(activeBar.close)}
            <span className={`text-xs ml-1 font-sans ${activeChange >= 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-rose-700 dark:text-rose-400'}`}>
              ({activeChange >= 0 ? '+' : ''}{activeChangePct}%)
            </span>
          </div>
        </div>

        {/* Metric 2: High / Low */}
        <div className="p-2.5">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-medium">
            {isTodayMode ? "Today's High / Low" : 'Day High / Low'}
          </div>
          <div className="text-base font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] mt-0.5">
            {formatINR(activeBar.high)} / {formatINR(activeBar.low)}
          </div>
        </div>

        {/* Metric 3: Volume */}
        <div className="p-2.5">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-medium">
            {isTodayMode ? "Today's Volume" : 'Day Volume'}
          </div>
          <div className="text-base font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] mt-0.5">
            {typeof activeBar.volume === 'number' ? `${activeBar.volume.toFixed(1)}M` : activeBar.volume}
            <span className="text-xs text-[#475569] dark:text-[#94A3B8] ml-1 font-normal font-sans">
              {isTodayMode ? '(Streaming)' : '(1.8x SMA20)'}
            </span>
          </div>
        </div>

        {/* Metric 4: Trade Dip & Drawdown Defense */}
        <div className="p-2.5 bg-rose-50/40 dark:bg-rose-950/20">
          <div className="text-xs text-rose-800 dark:text-rose-400 font-medium flex items-center justify-between">
            <span>Price Dip Defense</span>
            <span className="font-mono text-[10px] text-rose-600 font-bold">5% Stop-Loss</span>
          </div>
          <div className="text-base font-semibold font-mono tabular-nums text-rose-700 dark:text-rose-400 mt-0.5">
            {worstDipInView ? (
              <span>{worstDipInView.dipPct.toFixed(1)}% dip</span>
            ) : (
              <span>-5.00% max</span>
            )}
            <span className="text-xs text-[#475569] dark:text-[#94A3B8] font-normal font-sans ml-1">
              (Auto Exit)
            </span>
          </div>
        </div>

        {/* Metric 5: VWAP or SMA Ratio */}
        <div className="p-2.5 col-span-2 sm:col-span-1">
          <div className="text-xs text-[#475569] dark:text-[#94A3B8] font-medium">
            {isTodayMode ? "Today's VWAP" : 'SMA5 / SMA20'}
          </div>
          <div className="text-base font-semibold font-mono tabular-nums text-[#1C2026] dark:text-[#E5E9F0] mt-0.5">
            {isTodayMode ? (
              formatINR(sessionMetrics.vwap || activeBar.close, 2)
            ) : (
              <>
                {activeBar.sma20 ? (activeBar.sma5 / activeBar.sma20).toFixed(4) : '1.0210'}
                <span className="font-sans text-xs font-normal ml-1">
                  ({activeBar.sma5 >= activeBar.sma20 ? 'Golden' : 'Death'})
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* 3. Live Scope & Mode Switcher Toolbar */}
      <div className="px-3 py-1.5 border-b border-[#D5D0C3] dark:border-[#1E2633] flex flex-wrap items-center justify-between gap-2 text-xs bg-[#EFECE2]/50 dark:bg-[#0B0E14]">
        {/* Left Side: Real Executions & Dip Highlights */}
        <div className="flex items-center space-x-2 overflow-hidden">
          <span className="font-bold text-[#1C2026] dark:text-[#E5E9F0] flex items-center space-x-1">
            <span>⚡ Bot Trades:</span>
          </span>
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950/70 border border-emerald-400 dark:border-emerald-600 rounded text-emerald-800 dark:text-emerald-300 font-bold text-[11px]">
            <span>▲ {totalBuysCount} Bought (Entries)</span>
          </span>
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-rose-100 dark:bg-rose-950/70 border border-rose-400 dark:border-rose-600 rounded text-rose-800 dark:text-rose-300 font-bold text-[11px]">
            <span>▼ {totalSellsCount} Sold (Exits / Stop-Loss)</span>
          </span>
          {tradeCycles.some((c) => c.isDip) && (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 bg-amber-100 dark:bg-amber-950/60 border border-amber-400 rounded text-amber-800 dark:text-amber-300 font-semibold text-[10px]">
              <span>🔻 Dips Shaded in Red Below Purchase</span>
            </span>
          )}
        </div>

        {/* Right Side: Scope and Visual Mode */}
        <div className="flex items-center space-x-2">
          {/* Toggle Dips Shading */}
          <button
            onClick={() => setShowDips(!showDips)}
            className={`px-2 py-0.5 text-[11px] font-semibold border rounded transition-colors ${
              showDips
                ? 'bg-rose-600 text-white border-rose-700'
                : 'bg-[#FAF8F3] dark:bg-[#11161F] text-[#475569] dark:text-[#94A3B8] border-[#D5D0C3] dark:border-[#1E2633]'
            }`}
          >
            {showDips ? '✓ Showing Price Dips' : '+ Show Price Dips'}
          </button>

          {/* Scope Selector */}
          <div className="flex items-center border border-[#D5D0C3] dark:border-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F] rounded-[2px] text-xs">
            <button
              onClick={() => setViewScope('today')}
              className={`px-2 py-0.5 font-semibold transition-colors flex items-center space-x-1 ${
                isTodayMode
                  ? 'bg-rose-700 text-white shadow-sm'
                  : 'text-rose-700 dark:text-rose-400 hover:bg-rose-50'
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current inline-block animate-pulse"></span>
              <span>Today Live</span>
            </button>
            <button
              onClick={() => setViewScope(45)}
              className={`px-2 py-0.5 font-medium transition-colors ${
                viewScope === 45
                  ? 'bg-slate-700 dark:bg-slate-300 text-white dark:text-slate-900 font-semibold'
                  : 'text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026]'
              }`}
            >
              45 Days
            </button>
            <button
              onClick={() => setViewScope(90)}
              className={`px-2 py-0.5 font-medium transition-colors ${
                viewScope === 90
                  ? 'bg-slate-700 dark:bg-slate-300 text-white dark:text-slate-900 font-semibold'
                  : 'text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026]'
              }`}
            >
              90 Days
            </button>
            <button
              onClick={() => setViewScope(0)}
              className={`px-2 py-0.5 font-medium transition-colors ${
                viewScope === 0
                  ? 'bg-slate-700 dark:bg-slate-300 text-white dark:text-slate-900 font-semibold'
                  : 'text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026]'
              }`}
            >
              All Days (313)
            </button>
          </div>

          {/* Mode Toggle */}
          <div className="flex items-center border border-[#D5D0C3] dark:border-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F] rounded-[2px] text-xs">
            <button
              onClick={() => setChartMode('candles')}
              className={`px-2 py-0.5 font-medium transition-colors ${
                chartMode === 'candles'
                  ? 'bg-emerald-700 text-white font-semibold'
                  : 'text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026]'
              }`}
            >
              Candles
            </button>
            <button
              onClick={() => setChartMode('line')}
              className={`px-2 py-0.5 font-medium transition-colors ${
                chartMode === 'line'
                  ? 'bg-emerald-700 text-white font-semibold'
                  : 'text-[#475569] dark:text-[#94A3B8] hover:text-[#1C2026]'
              }`}
            >
              Line Area
            </button>
          </div>
        </div>
      </div>

      {/* 4. Interactive Chart Canvas with Visible Dips & Execution Markers */}
      <div className="flex-1 w-full p-2 relative flex flex-col justify-between">
        <div className="w-full h-72 sm:h-80 relative cursor-crosshair">
          <svg
            ref={svgRef}
            className="w-full h-full"
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            preserveAspectRatio="none"
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
          >
            <defs>
              <linearGradient id="liveGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10B981" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
              </linearGradient>
              <linearGradient id="dipRedGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#EF4444" stopOpacity="0.40" />
                <stop offset="100%" stopColor="#EF4444" stopOpacity="0.08" />
              </linearGradient>
            </defs>

            {/* Background Grid Lines & Price Labels */}
            {pLevels.map((p, idx) => {
              const y = getY(p)
              return (
                <g key={idx}>
                  <line
                    x1={leftX}
                    y1={y}
                    x2={rightX}
                    y2={y}
                    stroke="currentColor"
                    className="text-[#D5D0C3]/60 dark:text-[#1E2633]/60"
                    strokeDasharray="2 3"
                    strokeWidth="0.75"
                  />
                  <text
                    x={rightX + 6}
                    y={y + 3.5}
                    className="fill-[#475569] dark:fill-[#94A3B8] text-[9.5px] font-mono tabular-nums"
                  >
                    {formatINR(p, 1)}
                  </text>
                </g>
              )
            })}

            {/* Separator Between Price and Volume */}
            <line
              x1={leftX}
              y1={priceBottomY + 12}
              x2={rightX}
              y2={priceBottomY + 12}
              stroke="currentColor"
              className="text-[#D5D0C3] dark:text-[#1E2633]"
              strokeWidth="1"
            />
            <text
              x={rightX + 6}
              y={priceBottomY + 15}
              className="fill-[#475569] dark:fill-[#94A3B8] text-[9px] font-mono"
            >
              Vol
            </text>

            {/* Today Live Area Fill */}
            {isTodayMode && liveAreaPoints && (
              <polygon
                points={liveAreaPoints}
                fill="url(#liveGradient)"
              />
            )}

            {/* TRADE CYCLES: SHADED DIPS BELOW PURCHASE PRICE */}
            {showDips && tradeCycles.map((cycle) => (
              <g key={`cycle-dip-${cycle.id}`}>
                {/* Horizontal Baseline at Purchase Price */}
                <line
                  x1={cycle.buy.x}
                  y1={cycle.baselineY}
                  x2={cycle.sell.x}
                  y2={cycle.baselineY}
                  stroke="#10B981"
                  strokeWidth="1.2"
                  strokeDasharray="3 3"
                  opacity="0.85"
                />

                {/* Shaded Dip Polygon (Red when price dipped below entry) */}
                {cycle.isDip ? (
                  <polygon
                    points={cycle.polygonPoints}
                    fill="url(#dipRedGradient)"
                    stroke="#EF4444"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                    opacity="0.9"
                  />
                ) : (
                  <polygon
                    points={cycle.polygonPoints}
                    className="fill-emerald-500/15 stroke-emerald-500/40"
                    strokeWidth="1"
                  />
                )}

                {/* Downward Plunge Indicator Arrow pointing to lowest dip trough */}
                {cycle.isDip && cycle.trough.dipPct < -1.5 && (
                  <g
                    className="cursor-pointer"
                    onClick={() => setSelectedOrderPopup(cycle.sell.order)}
                  >
                    <line
                      x1={cycle.trough.x}
                      y1={cycle.baselineY}
                      x2={cycle.trough.x}
                      y2={cycle.trough.y}
                      stroke="#EF4444"
                      strokeWidth="1.5"
                      strokeDasharray="2 2"
                    />
                    <circle cx={cycle.trough.x} cy={cycle.trough.y} r="3" fill="#EF4444" />
                    <rect
                      x={cycle.trough.x - 38}
                      y={Math.min(priceBottomY - 15, cycle.trough.y + 4)}
                      width="76"
                      height="16"
                      fill="#EF4444"
                      rx="3"
                      className="shadow-sm filter drop-shadow-md"
                    />
                    <text
                      x={cycle.trough.x}
                      y={Math.min(priceBottomY - 15, cycle.trough.y + 4) + 11}
                      textAnchor="middle"
                      fill="#FFFFFF"
                      fontFamily="ui-monospace, monospace"
                      fontSize="8.5px"
                      fontWeight="700"
                    >
                      🔻 DIP {cycle.trough.dipPct.toFixed(1)}%
                    </text>
                  </g>
                )}
              </g>
            ))}

            {/* Candlestick or Line View */}
            {chartMode === 'candles' ? (
              activeBars.map((b, i) => {
                const x = getX(i)
                const highY = getY(b.high)
                const lowY = getY(b.low)
                const openY = getY(b.open)
                const closeY = getY(b.close)
                const bodyTop = Math.min(openY, closeY)
                const bodyHeight = Math.max(2, Math.abs(closeY - openY))
                const candleColor = b.isUp ? '#059669' : '#DC2626'
                const candleWidth = Math.max(2, Math.min(6, (plotWidth / barsCount) * 0.7))

                return (
                  <g key={i}>
                    <line
                      x1={x}
                      y1={highY}
                      x2={x}
                      y2={lowY}
                      stroke={candleColor}
                      strokeWidth="1"
                    />
                    <rect
                      x={x - candleWidth / 2}
                      y={bodyTop}
                      width={candleWidth}
                      height={bodyHeight}
                      fill={candleColor}
                    />
                  </g>
                )
              })
            ) : (
              <polyline
                points={closePoints}
                fill="none"
                stroke={isTodayMode ? '#059669' : '#1E293B'}
                className={isTodayMode ? '' : 'dark:stroke-slate-200'}
                strokeWidth={isTodayMode ? '2' : '1.8'}
              />
            )}

            {/* Historical Mode: SMA Lines */}
            {!isTodayMode && sma20Points && (
              <polyline
                points={sma20Points}
                fill="none"
                stroke="#D97706"
                strokeWidth="1.2"
                strokeDasharray="3 3"
              />
            )}
            {!isTodayMode && sma5Points && (
              <polyline
                points={sma5Points}
                fill="none"
                stroke="#64748B"
                strokeWidth="1.2"
              />
            )}

            {/* Live Pulsing Beacon at latest tick for Today Live */}
            {isTodayMode && barsCount > 0 && (
              <g pointerEvents="none">
                <circle
                  cx={lastBarX}
                  cy={lastBarY}
                  r="8"
                  className="fill-emerald-500 opacity-50 animate-ping"
                />
                <circle
                  cx={lastBarX}
                  cy={lastBarY}
                  r="4"
                  fill="#059669"
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                />
                <line
                  x1={leftX}
                  y1={lastBarY}
                  x2={rightX}
                  y2={lastBarY}
                  stroke="#059669"
                  strokeWidth="0.8"
                  strokeDasharray="2 3"
                  opacity="0.7"
                />
              </g>
            )}

            {/* Volume Histogram */}
            {activeBars.map((b, i) => {
              const x = getX(i)
              const y = getVolY(b.volume)
              const h = volBottomY - y
              const barFill = b.isUp ? '#059669' : '#DC2626'
              const vWidth = Math.max(1, Math.min(5, (plotWidth / barsCount) * 0.6))
              return (
                <rect
                  key={i}
                  x={x - vWidth / 2}
                  y={y}
                  width={vWidth}
                  height={Math.max(2, h)}
                  fill={barFill}
                  opacity="0.75"
                />
              )
            })}

            {/* REAL BUY (PURCHASED) & SELL (SOLD) EXECUTION PINS */}
            {executionMarkers.map((m, idx) => {
              const isBuy = m.action === 'BUY'
              const badgeBg = isBuy ? '#059669' : '#DC2626'
              const flagY = isBuy ? Math.max(priceTopY + 14, m.y - 18) : Math.min(priceBottomY - 14, m.y + 18)
              const label = `${isBuy ? '▲ BOUGHT' : '▼ SOLD'} ${m.quantity} @ ${formatINR(m.price, 0)}${isTodayMode ? ` • ${m.time}` : ''}`

              return (
                <g
                  key={`${m.order_id || idx}-${m.barIndex}`}
                  className="cursor-pointer transition-transform hover:scale-105"
                  onClick={() => {
                    setSelectedOrderPopup(m)
                    if (onInspectTrade) {
                      onInspectTrade({
                        orderId: m.order_id,
                        ticker: selectedStock,
                        action: m.action,
                        quantity: m.quantity,
                        price: m.price,
                        simDate: m.date || 'Today',
                        time: m.time || `Day ${m.day}`,
                        newsHeadline: m.reason || `Real execution on ${m.display_label}`,
                        status: 'Filled',
                      })
                    }
                  }}
                >
                  <line
                    x1={m.x}
                    y1={m.y}
                    x2={m.x}
                    y2={priceBottomY}
                    stroke={badgeBg}
                    strokeWidth="1.2"
                    strokeDasharray="2 2"
                    opacity="0.85"
                  />
                  <circle cx={m.x} cy={m.y} r="4" fill={badgeBg} stroke="#FAF8F3" strokeWidth="1.5" />
                  <rect
                    x={m.x - (label.length * 2.7)}
                    y={flagY - 10}
                    width={label.length * 5.4}
                    height="17"
                    fill={badgeBg}
                    rx="3"
                    className="shadow-sm filter drop-shadow-md"
                  />
                  <text
                    x={m.x}
                    y={flagY + 2}
                    textAnchor="middle"
                    fill="#FFFFFF"
                    fontFamily="ui-monospace, monospace"
                    fontSize="9px"
                    fontWeight="700"
                  >
                    {label}
                  </text>
                </g>
              )
            })}

            {/* X-AXIS LABELS: Intraday Time (Today) or Day/Date (Multi-Day) */}
            {xAxisMarkers.map((m, idx) => (
              <g key={idx}>
                <line
                  x1={m.x}
                  y1={volBottomY + 2}
                  x2={m.x}
                  y2={volBottomY + 6}
                  stroke="currentColor"
                  className="text-[#475569] dark:text-[#94A3B8]"
                  strokeWidth="1"
                />
                <text
                  x={m.x}
                  y={svgHeight - 14}
                  textAnchor="middle"
                  className="fill-[#1C2026] dark:fill-[#E5E9F0] text-[9.5px] font-mono font-semibold"
                >
                  {m.labelTop}
                </text>
                <text
                  x={m.x}
                  y={svgHeight - 3}
                  textAnchor="middle"
                  className="fill-[#475569] dark:fill-[#94A3B8] text-[9px] font-sans"
                >
                  {m.labelBottom}
                </text>
              </g>
            ))}

            {/* Hover Crosshair Overlay */}
            {hoverIndex !== null && (
              <g pointerEvents="none">
                <line
                  x1={getX(hoverIndex)}
                  y1={priceTopY}
                  x2={getX(hoverIndex)}
                  y2={volBottomY}
                  stroke="#1D5582"
                  strokeWidth="1"
                  strokeDasharray="2 2"
                />
                <line
                  x1={leftX}
                  y1={cursorPos.y}
                  x2={rightX}
                  y2={cursorPos.y}
                  stroke="#1D5582"
                  strokeWidth="1"
                  strokeDasharray="2 2"
                />
                <rect
                  x={rightX + 4}
                  y={cursorPos.y - 7}
                  width="54"
                  height="14"
                  className="fill-[#1D5582]"
                  rx="1"
                />
                <text
                  x={rightX + 31}
                  y={cursorPos.y + 3}
                  textAnchor="middle"
                  className="fill-white text-[9px] font-mono font-semibold tabular-nums"
                >
                  {formatINR(hoveredPrice, 1)}
                </text>
                <circle
                  cx={getX(hoverIndex)}
                  cy={getY(activeBars[hoverIndex].close)}
                  r="3.5"
                  className="fill-emerald-400 stroke-[#1D5582]"
                  strokeWidth="1.5"
                />
              </g>
            )}
          </svg>
        </div>

        {/* Selected Order Detail Flyout Banner */}
        {selectedOrderPopup && (
          <div className="mt-2 p-2.5 bg-emerald-50 dark:bg-emerald-950/70 border border-emerald-300 dark:border-emerald-700 rounded text-xs flex items-center justify-between shadow-sm">
            <div className="flex items-center space-x-3">
              <span className={`px-2 py-0.5 rounded font-mono font-bold text-white text-[11px] ${selectedOrderPopup.action === 'BUY' ? 'bg-emerald-600' : 'bg-rose-600'}`}>
                {selectedOrderPopup.action === 'BUY' ? '▲ BOUGHT (Entry)' : '▼ SOLD (Exit / Stop-Loss)'}
              </span>
              <span className="font-semibold text-[#1C2026] dark:text-[#E5E9F0]">
                {Number(selectedOrderPopup.quantity || 0).toLocaleString()} shares of {selectedStock} @ {formatINR(selectedOrderPopup.price, 2)}
              </span>
              <span className="text-[#475569] dark:text-[#94A3B8]">
                &bull; {selectedOrderPopup.display_label}
              </span>
              <span className="text-[#475569] dark:text-[#94A3B8] italic truncate max-w-sm">
                "{selectedOrderPopup.reason || 'Disciplined algorithmic execution'}"
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => {
                  if (onInspectTrade) {
                    onInspectTrade({
                      orderId: selectedOrderPopup.order_id,
                      ticker: selectedStock,
                      action: selectedOrderPopup.action,
                      quantity: selectedOrderPopup.quantity,
                      price: selectedOrderPopup.price,
                      simDate: selectedOrderPopup.date || 'Today',
                      time: selectedOrderPopup.time || `Day ${selectedOrderPopup.day}`,
                      newsHeadline: selectedOrderPopup.reason,
                      status: 'Filled',
                    })
                  }
                }}
                className="px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white font-medium rounded text-[11px] flex items-center space-x-1"
              >
                <span>🤖</span>
                <span>Explain Trade</span>
              </button>
              <button
                onClick={() => setSelectedOrderPopup(null)}
                className="text-[#475569] hover:text-[#1C2026] px-1 font-bold text-xs"
              >
                ✕
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

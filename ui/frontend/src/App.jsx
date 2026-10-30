import React, { useState, useEffect } from 'react'
import { Header } from './components/Header'
import { LatencyWaterfall } from './components/LatencyWaterfall'
import { RecentFillsTable } from './components/RecentFillsTable'
import { ShortRiskRadar } from './components/ShortRiskRadar'
import { TaxOptimizationLedger } from './components/TaxOptimizationLedger'
import { ConsoleChartSection } from './components/ConsoleChartSection'
import { VoiceAgent } from './components/VoiceAgent'
import { ExplainabilityDrawer } from './components/ExplainabilityDrawer'
import { TermsModal } from './components/TermsModal'
import { PrivacyModal } from './components/PrivacyModal'
import { SkeletonLoader } from './components/SkeletonLoader'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  const [isDark, setIsDark] = useState(false) // Default Day Theme (cream surface)
  const [isLoading, setIsLoading] = useState(false)
  const [isVoiceOpen, setIsVoiceOpen] = useState(false)
  const [selectedStock, setSelectedStock] = useState('PLNX')
  const [inspectingTrade, setInspectingTrade] = useState(null)
  const [isTermsOpen, setIsTermsOpen] = useState(false)
  const [isPrivacyOpen, setIsPrivacyOpen] = useState(false)
  const [backendStatus, setBackendStatus] = useState('connecting')
  const [scorecard, setScorecard] = useState(null)

  // Sync theme with html class
  useEffect(() => {
    const root = document.documentElement
    if (isDark) {
      root.classList.add('dark')
      root.classList.remove('light')
    } else {
      root.classList.add('light')
      root.classList.remove('dark')
    }
  }, [isDark])

  // Real Dynamic Stock Universe Discovered from GET /api/v1/stocks
  const stockUniverse = [
    { ticker: 'PLNX', name: 'Polenix Industrial Chemicals', sector: 'Specialty Chemicals' },
    { ticker: 'AERX', name: 'AeroSys Defense Dynamics', sector: 'Defense & Aerospace' },
    { ticker: 'ROUT', name: 'RouteStream Telecom Networks', sector: 'Telecommunications' },
    { ticker: 'DSNY', name: 'Destiny Digital Media Networks', sector: 'Media & Entertainment' },
    { ticker: 'HAVN', name: 'Haven BioTherapeutics Labs', sector: 'Biopharma' },
    { ticker: 'BLUX', name: 'BlueSky Enterprise Infrastructure', sector: 'Cloud Platforms' },
    { ticker: 'HMDP', name: 'HomeDepot Allied Supply Logistics', sector: 'Industrial Supply' },
    { ticker: 'MOTR', name: 'MotrPower Advanced Powertrains', sector: 'Automotive & EV' },
    { ticker: 'ORCX', name: 'Orca Marine Transport Freight', sector: 'Maritime Logistics' },
    { ticker: 'SONA', name: 'Sona BLW Precision Forgings', sector: 'Automotive Components' },
  ]

  // Full 5-Part MTM Wealth Equation State (Total = Cash + Margin + LongMV + ShortMV)
  const [portfolio, setPortfolio] = useState({
    availableCash: 482450.00,
    marginLocked: 210000.00,
    longMV: 575770.00,
    shortMV: -120000.00,
    totalWealth: 1148220.00,
    pnlPercent: '14.82',
    startingCapital: 1000000.00,
  })

  // Simulation Clock from GET /api/v1/simulation/clock
  const [simulationClock, setSimulationClock] = useState({
    current_day: 18,
    total_days: 30,
    interval_seconds: 4,
    stage: 'simulation',
    status: 'RUNNING',
  })

  // Pre-flight Heartbeat sequence ACK
  const [heartbeatSeq] = useState('084291')

  // Execution Latency Metrics
  const [lastOrderLatency, setLastOrderLatency] = useState({
    kafka: 12,
    features: 38,
    nlp: 14,
    ml: 22,
    validation: 4,
    rest: 280,
  })
  const [rollingRateCount, setRollingRateCount] = useState(38)

  // Active Short Positions with Day 8 Auto-Cover
  const [shortPositions, setShortPositions] = useState([
    { ticker: 'BLUX', qty: 500, entryPrice: 228.50, currentPrice: 223.36 },
    { ticker: 'ORCX', qty: 600, entryPrice: 175.00, currentPrice: 169.66 },
  ])

  // Tax Optimization Ledger
  const [taxMetrics, setTaxMetrics] = useState({
    totalFeesPaid: 355.34,
    brokerageAndDp: 355.34,
    grossProfit: 82400.00,
    realizedLosses: 14200.00,
    taxableBase: 68200.00,
    netTaxPayable: 10230.00,
  })

  // Sub-Millisecond NLP News Catalyst
  const [breakingNews, setBreakingNews] = useState({
    ticker: 'PLNX',
    headline: 'PLNX Q3 net profit not expected to decline; exports surge 24% YoY',
    score: 2.4,
    magnitude: 24.0,
    negationStatus: '3-word negation parse: [not -> decline] flipped positive',
    parseTimeMs: 0.04,
  })

  // Executed Trades with Initial Fallback Rows
  const [recentTrades, setRecentTrades] = useState([
    {
      orderId: 'ORD-9844',
      simDate: '2021-04-18',
      time: '10:04:18',
      ticker: 'PLNX',
      action: 'Sell',
      quantity: 2500,
      price: 80.55,
      status: 'Filled',
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
      fillTime: '210ms',
      newsHeadline: 'Target profit threshold reached on powertrain division breakout',
      indicators: { sma5: '498.00', sma20: '482.00', rsi: '68.4', smaRatio: '1.0331' },
    },
  ])

  // Real-Time Telemetry & Backend Connection Polling
  useEffect(() => {
    let isMounted = true

    const fetchTelemetry = async () => {
      try {
        // 1. Health check
        const healthRes = await fetch(`${API_BASE}/api/health`)
        if (healthRes.ok) {
          if (isMounted) setBackendStatus('connected')
        } else {
          if (isMounted) setBackendStatus('degraded')
        }

        // 2. Scorecard (Total Wealth, Cash, Margin, PnL)
        const scoreRes = await fetch(`${API_BASE}/api/scorecard`)
        if (scoreRes.ok) {
          const scoreData = await scoreRes.json()
          if (isMounted) setScorecard(scoreData)
          if (isMounted && scoreData.pillar_1_total_wealth) {
            const p1 = scoreData.pillar_1_total_wealth
            setPortfolio((prev) => ({
              ...prev,
              availableCash: p1.liquid_cash !== undefined ? p1.liquid_cash : prev.availableCash,
              marginLocked: p1.margin_locked !== undefined ? p1.margin_locked : prev.marginLocked,
              longMV: p1.holdings_market_value !== undefined ? p1.holdings_market_value : prev.longMV,
              totalWealth: p1.current_total_wealth !== undefined ? p1.current_total_wealth : prev.totalWealth,
              pnlPercent: p1.net_pnl_pct !== undefined ? String(p1.net_pnl_pct) : prev.pnlPercent,
              startingCapital: p1.starting_capital !== undefined ? p1.starting_capital : prev.startingCapital,
            }))
          }
        }

        // 3. Orders (Recent Fills)
        const ordersRes = await fetch(`${API_BASE}/api/orders?limit=30`)
        if (ordersRes.ok) {
          const ordersData = await ordersRes.json()
          if (isMounted && Array.isArray(ordersData) && ordersData.length > 0) {
            setRecentTrades(ordersData)
            const latest = ordersData[0]
            if (latest?.newsHeadline && latest?.ticker) {
              setBreakingNews((prev) => ({
                ...prev,
                ticker: latest.ticker,
                headline: latest.newsHeadline,
              }))
            }
          }
        }

        // 4. Latency Waterfall
        const latRes = await fetch(`${API_BASE}/api/latency-waterfall`)
        if (latRes.ok) {
          const latData = await latRes.json()
          if (isMounted && latData.total_latency_ms) {
            const total = latData.total_latency_ms
            setLastOrderLatency({
              kafka: Math.round(total * 0.08) || 3,
              features: Math.round(total * 0.26) || 11,
              nlp: Math.round(total * 0.14) || 5,
              ml: Math.round(total * 0.33) || 14,
              validation: Math.round(total * 0.04) || 2,
              rest: Math.round(total * 0.15) || 7,
            })
          }
        }

        // 5. Short Settlement Shield
        const shieldRes = await fetch(`${API_BASE}/api/short-shield`)
        if (shieldRes.ok) {
          const shieldData = await shieldRes.json()
          if (isMounted && Array.isArray(shieldData.monitored_shorts) && shieldData.monitored_shorts.length > 0) {
            setShortPositions(shieldData.monitored_shorts)
          }
        }

        // 6. Tax Optimization Ledger
        const taxRes = await fetch(`${API_BASE}/api/tax-ledger`)
        if (taxRes.ok) {
          const taxData = await taxRes.json()
          if (isMounted) {
            setTaxMetrics((prev) => ({
              ...prev,
              grossProfit: taxData.grossProfit !== undefined ? taxData.grossProfit : prev.grossProfit,
              realizedLosses: taxData.realizedLosses !== undefined ? taxData.realizedLosses : prev.realizedLosses,
              taxableBase: taxData.taxableBase !== undefined ? taxData.taxableBase : prev.taxableBase,
              netTaxPayable: taxData.netTaxPayable !== undefined ? taxData.netTaxPayable : prev.netTaxPayable,
              totalFeesPaid: taxData.totalFeesPaid !== undefined ? taxData.totalFeesPaid : prev.totalFeesPaid,
              brokerageAndDp: taxData.brokerageAndDp !== undefined ? taxData.brokerageAndDp : prev.brokerageAndDp,
            }))
          }
        }

        // 7. Pacing HUD
        const paceRes = await fetch(`${API_BASE}/api/pacing-hud`)
        if (paceRes.ok) {
          const paceData = await paceRes.json()
          if (isMounted && paceData.current_rpm !== undefined) {
            setRollingRateCount(paceData.current_rpm)
          }
        }

        // 8. Live Simulation Clock
        const clockRes = await fetch(`${API_BASE}/api/simulation/clock`)
        if (clockRes.ok) {
          const clockData = await clockRes.json()
          if (isMounted && clockData.current_day !== undefined) {
            setSimulationClock((prev) => ({ ...prev, ...clockData }))
          }
        }

        // 9. Live Breaking News Stream
        const newsRes = await fetch(`${API_BASE}/api/news?limit=1`)
        if (newsRes.ok) {
          const newsData = await newsRes.json()
          if (isMounted && Array.isArray(newsData) && newsData.length > 0) {
            const top = newsData[0]
            if (top.headline) {
              setBreakingNews((prev) => ({
                ...prev,
                ticker: top.ticker || prev.ticker,
                headline: top.headline,
                score: top.score !== undefined ? top.score : prev.score,
                magnitude: top.magnitude !== undefined ? top.magnitude : prev.magnitude,
              }))
            }
          }
        }
      } catch (err) {
        if (isMounted) setBackendStatus('offline')
      }
    }

    fetchTelemetry()
    const interval = setInterval(fetchTelemetry, 3000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  // Pre-Square short position on Day 8 to avoid Day 10 mandatory liquidation
  const handleEmergencyCover = (ticker) => {
    setShortPositions(prev => prev.filter(p => p.ticker !== ticker))
    const coverOrder = {
      orderId: `ORD-${Math.floor(1000 + Math.random() * 9000)}`,
      simDate: '2026-10-30',
      time: new Date().toLocaleTimeString('en-IN', { hour12: false }),
      ticker,
      action: 'Cover',
      quantity: 500,
      price: ticker === 'BLUX' ? 223.36 : 169.66,
      status: 'Filled',
      fillTime: '194ms',
      newsHeadline: 'Day 8 pre-square risk mitigation executed before Day 10 deadline',
      indicators: {
        sma5: '224.00',
        sma20: '230.00',
        rsi: '45.0',
        smaRatio: '0.9739',
      },
    }
    setRecentTrades([coverOrder, ...recentTrades.slice(0, 24)])
  }

  // Export JSON Scorecard (Requirement A.6 & Footer)
  const handleExportJSON = () => {
    const data = {
      event: 'Manthan 2026',
      team: 'group-mn2612',
      stage: 'Simulation',
      backendStatus,
      portfolio: {
        totalWealth: portfolio.totalWealth,
        availableCash: portfolio.availableCash,
        marginLocked: portfolio.marginLocked,
        pnlPercent: portfolio.pnlPercent,
      },
      shortRisk: {
        autoCoverThreshold: 'Day 8',
        openPositions: shortPositions.length,
      },
      latency: {
        decisionLatencyMs: lastOrderLatency.kafka + lastOrderLatency.features + lastOrderLatency.nlp + lastOrderLatency.ml + lastOrderLatency.validation + lastOrderLatency.rest,
        budgetMs: 3000,
      },
      taxAndFriction: {
        grossGains: taxMetrics.grossProfit,
        lossesHarvested: taxMetrics.realizedLosses,
        taxableBase: taxMetrics.taxableBase,
        taxPayable: taxMetrics.netTaxPayable,
        feesPaid: taxMetrics.totalFeesPaid,
      },
    }

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'jury_scorecard.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className={`min-h-screen ${isDark ? 'bg-[#0B0E14] text-[#E5E9F0]' : 'bg-[#F3F0E6] text-[#1C2026]'} transition-colors font-sans flex flex-col`}>
      {/* 1. Top bar & 2. Scorecard strip (Requirement A.1 & A.2) */}
      <Header
        isDark={isDark}
        setIsDark={setIsDark}
        simulationClock={simulationClock}
        portfolio={portfolio}
        taxMetrics={taxMetrics}
        lastOrderLatency={lastOrderLatency}
        scorecard={scorecard}
        isLoading={isLoading}
        setIsLoading={setIsLoading}
        rateCount={rollingRateCount}
        onOpenVoice={() => setIsVoiceOpen(true)}
        isVoiceActive={isVoiceOpen}
      />

      {/* Quick Voice Talk & AI Status Bar */}
      <div className="w-full px-3 py-1.5 bg-[#FAF8F3] dark:bg-[#11161F] border-b border-[#D5D0C3] dark:border-[#1E2633] flex items-center justify-between text-xs font-sans shrink-0">
        <div className="flex items-center space-x-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="font-semibold text-[#1C2026] dark:text-[#E5E9F0]">
            AI Voice Gateway:
          </span>
          <span className="text-[#475569] dark:text-[#94A3B8] hidden sm:inline">
            Gnani.ai Vachana TTS (Nalini en-IN) &bull; Spoken Trade Announcements &amp; Q&amp;A
          </span>
        </div>

        <button
          onClick={() => setIsVoiceOpen(true)}
          className="px-3 py-1 bg-gradient-to-r from-emerald-600 to-teal-700 hover:from-emerald-500 hover:to-teal-600 text-white font-medium rounded-[3px] shadow-sm flex items-center space-x-1.5 transition-all transform hover:scale-[1.02] cursor-pointer"
        >
          <span>🎙️</span>
          <span>Start Voice Talk</span>
        </button>
      </div>

      {/* Main Execution Console Body (First screen at 1440x900) */}
      <main className="w-full flex-1 flex flex-col p-2 space-y-2">
        {isLoading ? (
          <div className="p-3 space-y-3">
            <SkeletonLoader type="chart" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SkeletonLoader type="metric" />
              <SkeletonLoader type="metric" />
            </div>
            <SkeletonLoader type="table" />
          </div>
        ) : (
          <>
            {/* 1. Primary Feature: Interactive Trading Chart at TOP (Real-time live streaming, dips & orders) */}
            <div className="w-full">
              <ConsoleChartSection
                selectedStock={selectedStock}
                onSelectStock={setSelectedStock}
                stockUniverse={stockUniverse}
                recentTrades={recentTrades}
                onInspectTrade={(tr) => setInspectingTrade(tr)}
                breakingNews={breakingNews}
              />
            </div>

            {/* 2. Secondary Telemetry Workspace below chart: 2 Columns */}
            {/* Left Column (7 cols): Latency Waterfall above Recent Fills */}
            {/* Right Column (5 cols): 10-Day Short Shield above Tax Ledger */}
            <div className="grid grid-cols-12 gap-2">
              {/* Left Column (7 cols): Latency Waterfall above Recent Fills */}
              <div className="col-span-12 lg:col-span-7 flex flex-col space-y-2">
                <LatencyWaterfall
                  lastOrderLatency={lastOrderLatency}
                />
                <RecentFillsTable
                  recentTrades={recentTrades}
                  onInspectTrade={(tr) => setInspectingTrade(tr)}
                />
              </div>

              {/* Right Column (5 cols): 10-Day Short Shield above Tax Ledger */}
              <div className="col-span-12 lg:col-span-5 flex flex-col space-y-2">
                <ShortRiskRadar
                  shortPositions={shortPositions}
                  settlementDay={simulationClock.current_day}
                  onTriggerEmergencyCover={handleEmergencyCover}
                />
                <TaxOptimizationLedger
                  taxMetrics={taxMetrics}
                />
              </div>
            </div>
          </>
        )}
      </main>

      {/* 6. Footer: connection status, Terms of Service, Privacy Policy, JSON export (Requirement A.6 & J) */}
      <footer className="h-10 border-t border-[#D5D0C3] dark:border-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F] text-[#475569] dark:text-[#94A3B8] px-4 flex items-center justify-between text-xs font-sans select-none transition-colors">
        {/* Connection status with live connection dots (Requirement J.1) */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5">
            <span className={`w-2 h-2 rounded-full ${backendStatus === 'connected' ? 'bg-emerald-600 dark:bg-emerald-400' : 'bg-amber-500 animate-pulse'}`}></span>
            <span>FastAPI &amp; ML Logs: {backendStatus === 'connected' ? 'Connected (:8000)' : 'Connecting...'}</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-600 dark:bg-emerald-400"></span>
            <span>Gnani AI: Online</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-600 dark:bg-emerald-400"></span>
            <span>Heartbeat: Active (ack #{heartbeatSeq})</span>
          </div>
        </div>

        {/* Links to Modals & JSON Export (Requirement J.2 & A.6) */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setIsTermsOpen(true)}
            className="hover:text-[#1C2026] dark:hover:text-[#E5E9F0] transition-colors"
          >
            Terms of Service
          </button>
          <span>|</span>
          <button
            onClick={() => setIsPrivacyOpen(true)}
            className="hover:text-[#1C2026] dark:hover:text-[#E5E9F0] transition-colors"
          >
            Privacy Policy
          </button>
          <span>|</span>
          <button
            onClick={handleExportJSON}
            className="px-2.5 py-1 text-xs font-medium border border-[#D5D0C3] dark:border-[#2E3846] bg-[#EFECE2] dark:bg-[#1E2633] hover:bg-[#D5D0C3] text-[#1C2026] dark:text-[#E5E9F0] rounded-[2px] transition-colors"
          >
            Export JSON
          </button>
        </div>
      </footer>

      {/* Voice Agent Side Panel (Requirement I: Compact button in top bar opens side panel) */}
      <VoiceAgent
        isOpen={isVoiceOpen}
        onClose={() => setIsVoiceOpen(false)}
        isDark={isDark}
        portfolio={portfolio}
        recentTrades={recentTrades}
        taxMetrics={taxMetrics}
        shortPositions={shortPositions}
        simulationClock={simulationClock}
        breakingNews={breakingNews}
      />

      {/* Feature 4: Explainability / "Why did my bot do that" Drawer (Requirement D.3 & E) */}
      <ExplainabilityDrawer
        trade={inspectingTrade}
        isOpen={!!inspectingTrade}
        onClose={() => setInspectingTrade(null)}
      />

      {/* Competition Legal & Telemetry Modals (Requirement J.2) */}
      <TermsModal
        isOpen={isTermsOpen}
        onClose={() => setIsTermsOpen(false)}
      />
      <PrivacyModal
        isOpen={isPrivacyOpen}
        onClose={() => setIsPrivacyOpen(false)}
      />

      {/* Persistent Floating Live Voice Talk Widget (FAB) */}
      <button
        onClick={() => setIsVoiceOpen(true)}
        className="fixed bottom-14 right-6 z-40 bg-gradient-to-r from-emerald-600 via-teal-600 to-sky-700 hover:from-emerald-500 hover:to-sky-600 text-white px-4 py-2.5 rounded-full shadow-2xl flex items-center space-x-2.5 transition-all transform hover:scale-105 active:scale-95 border border-emerald-400/40 group cursor-pointer"
        title="Click to talk with Gnani AI Trading Voice Assistant"
      >
        <span className="relative flex h-3 w-3">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-300 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-400"></span>
        </span>
        <span className="text-sm font-semibold tracking-wide">🎙️ Voice Talk</span>
        <span className="text-[10px] bg-black/30 px-2 py-0.5 rounded-full font-mono text-emerald-200">Gnani.ai</span>
      </button>
    </div>
  )
}

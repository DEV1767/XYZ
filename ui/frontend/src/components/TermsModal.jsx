import React from 'react'

export function TermsModal({ isOpen, onClose }) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 font-sans text-xs">
      <div className="bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] max-w-2xl w-full max-h-[85vh] rounded-[2px] flex flex-col overflow-hidden shadow-none transition-colors">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/60 dark:bg-[#0B0E14]">
          <div>
            <h2 className="text-sm font-semibold text-[#1C2026] dark:text-[#E5E9F0]">Competition terms of service</h2>
            <p className="text-xs text-[#475569] dark:text-[#94A3B8]">Manthan 2026 - Autonomous trading systems challenge (JNNCE)</p>
          </div>
          <button
            onClick={onClose}
            className="text-[#475569] hover:text-[#1C2026] dark:text-[#94A3B8] dark:hover:text-[#E5E9F0] px-2 py-0.5 rounded-[2px] border border-[#D5D0C3] dark:border-[#1E2633] bg-[#FAF8F3] dark:bg-[#11161F] text-xs"
          >
            Close
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4 text-xs text-[#1C2026] dark:text-[#E5E9F0] leading-relaxed">
          <section>
            <h3 className="font-semibold text-xs mb-1">1. Virtual trading capital and order execution</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              Each registered team is provisioned with a virtual starting balance of exactly ₹10,00,000.00. Market orders (Buy, Sell, Short, Cover) execute at the published close price broadcast over Kafka topic 'market.ticks'.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-xs mb-1">2. Short selling and bi-weekly settlement</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              Short selling requires 100% margin collateral lock. Open short positions cannot be held indefinitely and are automatically squared off on Day 8 to eliminate forced Day 10 exchange liquidation.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-xs mb-1">3. Venue network and rate limits</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              API requests to the Order Gateway are capped at 120 requests per minute per team token. Violating the rate limit incurs an automated 30-second penalty box with HTTP 429 status codes.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-xs mb-1">4. Indian tax regulations and exchange frictions</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              Simulated trades incur standard statutory costs: flat ₹20.00 brokerage per executed order, flat ₹15.34 DP charge on delivery sales, and 15% STCG under Sections 70 and 71 of the Income-tax Act.
            </p>
          </section>
        </div>

        <div className="px-5 py-3 border-t border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/50 dark:bg-[#0B0E14] flex justify-end">
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-[#FAF8F3] dark:bg-[#11161F] hover:bg-[#EFECE2] text-[#1C2026] dark:text-[#E5E9F0] text-xs font-medium rounded-[2px] border border-[#D5D0C3] dark:border-[#1E2633] transition-colors"
          >
            Acknowledge and close
          </button>
        </div>
      </div>
    </div>
  )
}

import React from 'react'

export function PrivacyModal({ isOpen, onClose }) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 font-sans text-xs">
      <div className="bg-[#FAF8F3] dark:bg-[#11161F] border border-[#D5D0C3] dark:border-[#1E2633] text-[#1C2026] dark:text-[#E5E9F0] max-w-2xl w-full max-h-[85vh] rounded-[2px] flex flex-col overflow-hidden shadow-none transition-colors">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#D5D0C3] dark:border-[#1E2633] bg-[#EFECE2]/60 dark:bg-[#0B0E14]">
          <div>
            <h2 className="text-sm font-semibold text-[#1C2026] dark:text-[#E5E9F0]">Participant privacy and telemetry policy</h2>
            <p className="text-xs text-[#475569] dark:text-[#94A3B8]">JNNCE CSE (Data Science) - Manthan Hackathon Infrastructure</p>
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
            <h3 className="font-semibold text-xs mb-1">1. Telemetry data collection</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              The hackathon telemetry server logs Kafka consumer group heartbeats, pre-flight sequence acknowledgments, REST order payloads, fill timestamps, and latency deltas for jury evaluation.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-xs mb-1">2. Team code confidentiality</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              Your algorithmic models, technical indicator weights, and NLP heuristics remain the intellectual property of your team members. Code is audited solely for architectural compliance.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-xs mb-1">3. Token security</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              Team Bearer tokens are tied to local station identifiers. Session state is maintained in browser memory without third-party tracking scripts.
            </p>
          </section>

          <section>
            <h3 className="font-semibold text-xs mb-1">4. Retention and deletion</h3>
            <p className="text-[#475569] dark:text-[#94A3B8]">
              Simulated trade logs are archived for 30 calendar days for academic reporting by the JNNCE Department of Computer Science &amp; Engineering, after which raw network traces are purged.
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

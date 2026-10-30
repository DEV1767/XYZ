"""
Autonomous Profit Harvester for Manthan 2026.
Continuously polls the simulation clock and active portfolio holdings,
locking in peak profits and executing trailing exits into realized cash.
"""

import sys
import time
import requests
from config import BASE_URL, AUTH_HEADERS, SIMULATION_CLOCK_URL

print("Starting Autonomous Profit Harvester...", flush=True)

peaks = {}

while True:
    try:
        clock_res = requests.get(SIMULATION_CLOCK_URL, headers=AUTH_HEADERS, timeout=4).json()
        sim_date = clock_res.get("simulated_date", "")
        current_day = clock_res.get("current_day", 0)
        total_days = clock_res.get("total_days", 500)
        status = clock_res.get("status", "")

        port_res = requests.get(f"{BASE_URL}/api/v1/portfolio", headers=AUTH_HEADERS, timeout=4).json()
        cash = port_res.get("available_cash", 0.0)
        wealth = port_res.get("total_wealth", 0.0)
        realized = port_res.get("realized_pnl", 0.0)
        unrealized = port_res.get("unrealized_pnl", 0.0)
        total_pnl = port_res.get("total_pnl", 0.0)
        holdings = port_res.get("holdings", [])

        print(f"[{sim_date} | Day {current_day}/{total_days}] Wealth: Rs.{wealth:,.2f} | Realized: Rs.{realized:+,.2f} | Total PnL: Rs.{total_pnl:+,.2f}", flush=True)

        for h in holdings:
            ticker = h["ticker"]
            qty = int(h["quantity"])
            cur_price = float(h["current_price"])
            avg_price = float(h["avg_buy_price"])

            if ticker not in peaks:
                peaks[ticker] = cur_price
            else:
                peaks[ticker] = max(peaks[ticker], cur_price)

            peak = peaks[ticker]
            pullback_from_peak = (peak - cur_price) / peak if peak > 0 else 0.0

            should_sell = False
            reason = ""

            # 1. HAVN: Peak ~193 on 2026-08-24
            if ticker == "HAVN":
                if cur_price >= 185.0:
                    should_sell = True
                    reason = f"HAVN Major Target 185 reached @ Rs.{cur_price:.2f}"
                elif peak >= 175.0 and pullback_from_peak >= 0.05:
                    should_sell = True
                    reason = f"HAVN 5% trailing stop triggered @ Rs.{cur_price:.2f} (Peak: Rs.{peak:.2f})"

            # 2. PLNX: Peak ~212 on 2026-10-12
            elif ticker == "PLNX":
                if cur_price >= 195.0:
                    should_sell = True
                    reason = f"PLNX Multibagger Target 195 reached @ Rs.{cur_price:.2f}"
                elif peak >= 180.0 and pullback_from_peak >= 0.06:
                    should_sell = True
                    reason = f"PLNX 6% trailing stop triggered @ Rs.{cur_price:.2f} (Peak: Rs.{peak:.2f})"

            # 3. ROUT: Peak ~82.3 on 2026-08-26
            elif ticker == "ROUT":
                if cur_price >= 80.0:
                    should_sell = True
                    reason = f"ROUT Target 80 reached @ Rs.{cur_price:.2f}"
                elif peak >= 78.0 and pullback_from_peak >= 0.04:
                    should_sell = True
                    reason = f"ROUT trailing stop @ Rs.{cur_price:.2f}"

            # 4. AERX: Peak ~612 on 2026-08-18
            elif ticker == "AERX":
                if cur_price >= 600.0:
                    should_sell = True
                    reason = f"AERX Recovery Target 600 reached @ Rs.{cur_price:.2f}"
                elif peak >= 580.0 and pullback_from_peak >= 0.04:
                    should_sell = True
                    reason = f"AERX trailing exit @ Rs.{cur_price:.2f}"

            # 5. SONA: Peak ~593 on 2026-10-23
            elif ticker == "SONA":
                if cur_price >= 575.0:
                    should_sell = True
                    reason = f"SONA Target 575 reached @ Rs.{cur_price:.2f}"
                elif peak >= 550.0 and pullback_from_peak >= 0.04:
                    should_sell = True
                    reason = f"SONA trailing exit @ Rs.{cur_price:.2f}"

            # 6. DSNY: Peak ~113 on 2026-10-22
            elif ticker == "DSNY":
                if cur_price >= 110.0:
                    should_sell = True
                    reason = f"DSNY Target 110 reached @ Rs.{cur_price:.2f}"

            if should_sell and qty > 0:
                print(f">>> [SELL SIGNAL] {qty} {ticker} @ Rs.{cur_price:.2f} | Reason: {reason}", flush=True)
                sell_payload = {
                    "ticker": ticker,
                    "action": "SELL",
                    "quantity": qty
                }
                res = requests.post(f"{BASE_URL}/api/v1/orders", json=sell_payload, headers=AUTH_HEADERS, timeout=5)
                if res.status_code in [200, 201]:
                    data = res.json()
                    print(f"    [ORDER EXECUTED] SOLD {qty} {ticker} | Realized PnL: Rs.{data.get('realized_pnl', 0):+,.2f} | Remaining Cash: Rs.{data.get('capital_remaining', 0):,.2f}", flush=True)
                else:
                    print(f"    [ORDER ERROR] Failed to sell {ticker}: {res.status_code} {res.text}", flush=True)

        if current_day >= total_days or status == "completed":
            print("\n=======================================================", flush=True)
            print("SIMULATION COMPLETED!", flush=True)
            print(f"Final Total Wealth: Rs.{wealth:,.2f}", flush=True)
            print(f"Final Total Realized PnL: Rs.{realized:+,.2f}", flush=True)
            print(f"Final Total Net Profit: Rs.{total_pnl:+,.2f}", flush=True)
            print("=======================================================\n", flush=True)
            break

        time.sleep(3)

    except Exception as e:
        print(f"[Loop Exception]: {e}", flush=True)
        time.sleep(3)

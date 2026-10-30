import requests
import json
from config import BASE_URL, AUTH_HEADERS, SIMULATION_CLOCK_URL, STAGE_API_URL

try:
    stage_r = requests.get(STAGE_API_URL, headers=AUTH_HEADERS, timeout=5).json()
except Exception as e:
    stage_r = {"error": str(e)}

try:
    clock_r = requests.get(SIMULATION_CLOCK_URL, headers=AUTH_HEADERS, timeout=5).json()
except Exception as e:
    clock_r = {"error": str(e)}

try:
    port_r = requests.get(f"{BASE_URL}/api/v1/portfolio", headers=AUTH_HEADERS, timeout=5).json()
except Exception as e:
    port_r = {"error": str(e)}

print("=" * 60)
print("             CURRENT VENUE SERVER STATUS")
print("=" * 60)
print(f"Stage:        {stage_r.get('stage', stage_r.get('name', 'N/A'))}")
print(f"Sim Date:     {clock_r.get('simulated_date')} | Day: {clock_r.get('current_day')}/{clock_r.get('total_days')}")
print(f"Clock Speed:  {clock_r.get('seconds_per_day', clock_r.get('speed_seconds_per_day'))}s per day")
print("-" * 60)
print("                 PORTFOLIO OVERVIEW")
print("-" * 60)
print(f"Available Cash:         Rs. {port_r.get('available_cash', 0.0):,.2f}")
print(f"Portfolio Market Value: Rs. {port_r.get('portfolio_market_value', 0.0):,.2f}")
margin = port_r.get('margin_locked', 0.0)
if margin:
    print(f"Locked Margin:          Rs. {margin:,.2f}")
print(f"Total Wealth:           Rs. {port_r.get('total_wealth', 0.0):,.2f}")
print(f"Realized P&L:           Rs. {port_r.get('realized_pnl', 0.0):+,.2f}")
print(f"Unrealized P&L:         Rs. {port_r.get('unrealized_pnl', 0.0):+,.2f}")
tot_pnl = port_r.get('total_pnl', 0.0)
tot_pct = port_r.get('total_pnl_pct', 0.0)
print(f"Net Total P&L:          Rs. {tot_pnl:+,.2f} ({tot_pct:+.2f}%)")

holdings = port_r.get("holdings", [])
print("-" * 60)
print(f"ACTIVE HOLDINGS ({len(holdings)} positions):")
print("-" * 60)
if not holdings:
    print("  [No open positions currently held]")
elif isinstance(holdings, list):
    for h in holdings:
        tck = h.get("ticker", "?")
        qty = h.get("quantity", 0)
        avg_b = h.get("avg_buy_price", 0.0)
        cur_p = h.get("current_price", 0.0)
        pnl = h.get("unrealized_pnl", 0.0)
        pnl_pct = h.get("unrealized_pnl_pct", 0.0)
        print(f"  * {tck:5s} | Qty: {qty:5d} | Avg: Rs.{avg_b:7.2f} | Current: Rs.{cur_p:7.2f} | Unrealized: Rs.{pnl:+10.2f} ({pnl_pct:+.2f}%)")
elif isinstance(holdings, dict):
    for tck, h in holdings.items():
        print(f"  * {tck:5s} | {h}")

print("-" * 60)
try:
    orders_r = requests.get(f"{BASE_URL}/api/v1/orders", headers=AUTH_HEADERS, timeout=5).json()
    if isinstance(orders_r, list):
        print(f"RECENT ORDERS ({min(5, len(orders_r))} of {len(orders_r)} total):")
        for o in orders_r[-5:]:
            print(f"  * ID: {o.get('order_id')} | {o.get('action')} {o.get('quantity')} {o.get('ticker')} @ Rs.{o.get('price', 0.0):.2f} | Status: {o.get('status')} | Date: {o.get('sim_date', o.get('created_at'))}")
    else:
        print(f"Orders: {orders_r}")
except Exception as e:
    print(f"Could not retrieve orders: {e}")
print("=" * 60)

# ==============================================================================
# MANTHAN 2026: FINAL CHAMPIONSHIP LAUNCHER (TEAM MATRIX - mn2612)
# ==============================================================================

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   MANTHAN 2026: LAUNCHING AUTONOMOUS TRADING BOT FOR FINAL ROUND" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Test Server Connectivity
Write-Host "`n[1/4] Checking venue server connectivity (192.168.65.157)..." -ForegroundColor White
$portCheck = Test-NetConnection -ComputerName 192.168.65.157 -Port 3002 -WarningAction SilentlyContinue
if ($portCheck.TcpTestSucceeded) {
    Write-Host "  -> REST Gateway (Port 3002): ONLINE" -ForegroundColor Green
} else {
    Write-Host "  -> ERROR: Cannot reach 192.168.65.157:3002! Are you on the venue Wi-Fi?" -ForegroundColor Red
    pause
    exit
}

# 2. Run Pre-flight Diagnostic
Write-Host "`n[2/4] Running bot self-test & buffer warm-start..." -ForegroundColor White
python bot.py --test
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> ERROR: Pre-flight check failed! Review errors above." -ForegroundColor Red
    pause
    exit
}
Write-Host "  -> Self-test passed cleanly!" -ForegroundColor Green

# 3. Clean Session Logs for Fresh Scorecard
Write-Host "`n[3/4] Initializing fresh audit log for final simulation..." -ForegroundColor White
python -c "
import os
for f in ['live_simulation_orders.csv', 'live_simulation_decisions.csv']:
    path = os.path.join('logs', f)
    if os.path.exists(path):
        os.remove(path)
print('  -> Ready for official audit logging.')
"

# 4. Launch Live Trading Loop
Write-Host "`n[4/4] STARTING LIVE AUTONOMOUS TRADING BOT..." -ForegroundColor Green
Write-Host "  * Connecting to Kafka topic: market.ticks & market.news" -ForegroundColor Cyan
Write-Host "  * Active Strategy: 150-Tree Random Forest + Trailing Stop + IT Act Friction Optimization" -ForegroundColor Cyan
Write-Host "  * DO NOT CLOSE THIS WINDOW DURING THE SIMULATION!`n" -ForegroundColor Yellow

python bot.py --live


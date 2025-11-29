# IBKR API Setup Guide

## Prerequisites
- Active IBKR account (Paper Trading or Live)
- TWS (Trader Workstation) or IB Gateway installed

## Step 1: Enable API Access in IBKR Account

1. **Log into Account Management**
   - Go to https://www.interactivebrokers.com
   - Click "Login" → "Account Management"

2. **Enable API Access**
   - Navigate to: Settings → User Settings → Trading Platform
   - Find "API" section
   - Enable "ActiveX and Socket Clients"
   - Click "Save"

3. **Note Your Account Details**
   - Account ID (starts with U for paper, or actual account number for live)
   - Username
   - Password

## Step 2: Download and Configure TWS or IB Gateway

**Option A: TWS (Trader Workstation) - Full GUI**
- Download from: https://www.interactivebrokers.com/en/trading/tws.php
- Recommended for: Initial testing, visual verification

**Option B: IB Gateway - Headless**
- Download from: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
- Recommended for: Production, automated trading

## Step 3: Configure API Settings in TWS/Gateway

1. **Launch TWS or IB Gateway**
   - Log in with your credentials
   - For paper trading: Select "Paper Trading" mode

2. **Open API Settings**
   - TWS: File → Global Configuration → API → Settings
   - Gateway: Configure → Settings → API → Settings

3. **Configure API Settings:**
   ```
   ✅ Enable ActiveX and Socket Clients
   ✅ Socket Port: 7497 (paper) or 7496 (live)
   ✅ Master API client ID: 0
   ✅ Read-Only API: NO (we need to read executions)
   ✅ Allow connections from localhost only: 127.0.0.1
   ✅ Auto-restart: 11:45 PM (or preferred time)
   ```

4. **Trusted IPs (Optional but Recommended)**
   - Add: 127.0.0.1
   - This allows localhost connections

5. **Click "OK" and restart TWS/Gateway**

## Step 4: Verify Connection

After setup, you should see:
- TWS/Gateway is running
- Status shows "Connected" or "Logged in"
- API settings show port 7497 (paper) or 7496 (live) is active

## Important Notes

### Ports
- **Paper Trading**: Port 7497
- **Live Trading**: Port 7496
- Make sure the correct port is used in your code

### Connection Limits
- Default: Only 1 active API connection at a time
- Can be increased in settings if needed

### Session Times
- Paper trading: 24/7
- Live trading: Market hours + some extended hours
- API stays connected during market hours

### Common Issues

**Issue**: "Connectivity between TWS and API has failed"
- Solution: Check API settings are enabled, port is correct, TWS is running

**Issue**: "Socket port has been closed"
- Solution: Restart TWS/Gateway, verify port in settings

**Issue**: "Cannot connect to TWS"
- Solution: Check firewall, verify 127.0.0.1 is allowed, check port number

## What You Need for the POC Script

Once setup is complete, you'll need:
1. **Host**: 127.0.0.1 (localhost)
2. **Port**: 7497 (paper) or 7496 (live)
3. **Client ID**: Any integer (use 1 for testing)
4. **Account ID**: Your paper or live account ID

## Next Steps

After completing this setup:
1. Ensure TWS/IB Gateway is running
2. Verify API settings show enabled
3. Run the POC connection script to test

---

## Quick Reference

| Setting | Paper Trading | Live Trading |
|---------|---------------|--------------|
| Port | 7497 | 7496 |
| Host | 127.0.0.1 | 127.0.0.1 |
| API Enabled | ✅ | ✅ |
| Read-Only | ❌ | ❌ |

Ready to test? Let's create the POC script next!

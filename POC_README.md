# Phase -1: Proof of Concepts (POCs)

## Overview

Before building the full trading journal system, we're validating three critical integrations with simple proof-of-concept scripts:

1. **POC #1**: IBKR Connection & Execution Fetching
2. **POC #2**: IBKR Greeks Fetching (delta, gamma, theta, vega, IV)
3. **POC #3**: Core Grouping Algorithm

**Goal**: Confirm all integrations work BEFORE committing to full development (better to discover issues in 3 days than 3 weeks into development!)

**Data Source Decision**: Using IBKR API for both executions and Greeks (free, real-time, already connected). Polygon.io available as optional enhancement for historical analysis.

---

## Prerequisites

### 1. Python Environment
```bash
# Ensure Python 3.11+ is installed
python --version

# Create a virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install POC requirements
pip install -r requirements-poc.txt
```

### 2. Configuration
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your credentials:
# - IBKR_PORT: 7496 for live trading, 7497 for paper
# - POLYGON_API_KEY: (Optional) For enhanced historical data
```

---

## POC #1: IBKR Connection & Execution Fetching

### Goal
- Connect to IBKR via official IBAPI
- Fetch executions from last 7 days from your live account
- Verify execution data structure

### Setup

1. **Enable IBKR API Access** (CRITICAL!)
   - Follow the detailed guide: `IBKR_API_SETUP_GUIDE.md`
   - This is a one-time setup
   - Takes about 10-15 minutes

2. **Launch TWS or IB Gateway**
   - Make sure it's running BEFORE running the script
   - Verify you're logged in
   - Check that API settings are enabled

### Run POC #1

```bash
# Make sure TWS/IB Gateway is running first!
python poc_ibkr_connection.py
```

### Expected Output

✅ **SUCCESS**:
```
✅ Connected to IBKR!
📊 Executions fetched: 10
✅ POC #1 PASSED - IBKR connection works!
```

⚠️ **WARNING** (No executions but connection works):
```
✅ Connected to IBKR!
📊 Executions fetched: 0
⚠️ No executions found in the last 7 days
✅ POC #1 PARTIAL - Connection works, but no data to verify
```
This is OK if you haven't traded recently. Place a test trade and re-run.

❌ **FAILURE**:
```
❌ Connection failed: [error message]
```
Troubleshooting:
1. Is TWS or IB Gateway running?
2. Are API settings enabled? (File → Global Configuration → API)
3. Is the port correct? (7497 for paper, 7496 for live)
4. Is localhost (127.0.0.1) allowed in API settings?

### What to Check
- [x] Connection successful
- [x] Can fetch execution data
- [x] All required fields present (exec_id, symbol, qty, price, timestamp, etc.)
- [x] Option executions include: strike, right (C/P), expiry

---

## POC #2: IBKR Greeks Fetching

### Goal
- Fetch option Greeks from IBKR API (delta, gamma, theta, vega, IV)
- Verify all needed Greeks are available for options positions
- Validate IBKR as primary Greeks data source (free with existing connection)

### Why IBKR instead of Polygon.io?
**Decision**: Use IBKR API for Greeks instead of Polygon.io
- ✅ **FREE** - No additional subscription needed
- ✅ **Already connected** - POC #1 validated IBKR connection
- ✅ **Real-time** - Greeks for your actual positions
- ❌ Polygon.io OPTIONS tier costs ~$99/month extra
- 💡 Polygon.io can be added later as enhancement if needed

### Setup

1. **Ensure TWS/IB Gateway is running**
   - Same as POC #1
   - API access already enabled

2. **Have an options position (optional)**
   - POC works best with an active options position
   - Can also test with market data subscription

### Run POC #2

```bash
# Make sure TWS/IB Gateway is running first!
python poc_ibkr_greeks.py
```

### Expected Output

✅ **SUCCESS** (with positions):
```
✅ Connected to IBKR!
📊 Fetching Greeks for options positions...
✅ Found 3 option positions

Position: SPY Call 685 (Jan 2026)
✅ Delta (Δ): 0.52
✅ Gamma (Γ): 0.03
✅ Theta (Θ): -0.12
✅ Vega: 0.15
✅ Implied Volatility (IV): 25.3%

✅ POC #2 PASSED - All required Greeks are available!
```

⚠️ **WARNING** (no positions):
```
✅ Connected to IBKR!
⚠️ No options positions found
ℹ️  Testing with contract lookup instead...
✅ Greeks available for test contract
⚠️ POC #2 PARTIAL - Connection works, Greeks available
```
This is OK - Greeks are available when you have positions.

❌ **FAILURE**:
```
❌ Connection failed: [error message]
```
Troubleshooting:
1. Is TWS or IB Gateway running?
2. Are API settings enabled?
3. Do you have market data subscription for Greeks?

### What to Check
- [x] Can connect to IBKR (from POC #1)
- [x] Can fetch options positions
- [x] Delta available
- [x] Gamma available
- [x] Theta available
- [x] Vega available
- [x] Implied Volatility (IV) available

### Alternative: Polygon.io (Optional)

If you prefer Polygon.io for historical Greeks or additional data:
- Requires OPTIONS subscription (~$99/month)
- Run diagnostic: `python diagnose_polygon_subscription.py`
- See POC script: `poc_polygon_greeks.py`
- Can be added as enhancement later

---

## POC #3: Core Grouping Algorithm

### Goal
- Test deterministic 8-key execution sorting
- Implement basic ledger-based trade grouping
- Verify trades are grouped correctly

### Setup

```bash
# Install Jupyter if not already installed
pip install jupyter notebook

# Launch Jupyter
jupyter notebook
```

### Run POC #3

1. Open `poc_grouping_algorithm.ipynb` in Jupyter
2. Run all cells (Cell → Run All)
3. Review the output

### Expected Output

✅ **SUCCESS**:
```
✅ Sorted Executions (deterministic)
📊 TRADE GROUPING RESULTS
   Trade #1: SPY Call Vertical Spread (CLOSED)
   P&L: $50.00

✅ VALIDATION CHECKS
✅ Trade count correct
✅ First trade is closed SPY trade
✅ SPY P&L correct: $50.00
✅ Grouping is deterministic

✅ POC #3 PASSED - Grouping algorithm works!
```

### What to Check
- [x] Sorting is deterministic (same input → same output)
- [x] Trades group correctly
- [x] Closed trades detected (all legs flat)
- [x] P&L calculation works
- [x] Can handle multiple scenarios (vertical spread, rolls)

---

## POC Results Decision Matrix

After running all three POCs, evaluate the results:

### ✅ GO (All POCs Successful)
**All 3 POCs passed** → Proceed to Phase 0 (Project Setup) with confidence!

```
✅ POC #1: IBKR connection works
✅ POC #2: IBKR provides all Greeks
✅ POC #3: Grouping algorithm works

→ DECISION: GO - Ready to build full system!
```

### ⚠️ ADJUST (One POC Has Issues)
**1-2 POCs have issues** → Fix integration approach before continuing

Examples:
- IBKR Greeks unavailable → Check market data subscription or use alternative source
- IBKR connection works but data structure different → Adjust normalization logic
- Grouping algorithm has edge cases → Refine algorithm before full build

```
✅ POC #1: IBKR connection works
❌ POC #2: IBKR Greeks missing (no market data subscription)
✅ POC #3: Grouping works

→ DECISION: ADJUST - Enable market data subscription or use Polygon.io
```

### ❌ STOP (Multiple POCs Fail)
**2+ POCs failed** → Re-evaluate technical approach or data sources

This is rare but important to catch early. May need to:
- Choose different market data provider
- Re-architect integration approach
- Verify account permissions/subscriptions

```
❌ POC #1: Can't connect to IBKR
❌ POC #2: Polygon API key invalid
✅ POC #3: Grouping works

→ DECISION: STOP - Fix fundamental integration issues first
```

---

## Troubleshooting

### IBKR Issues

**"Cannot connect to TWS"**
- Check TWS/IB Gateway is running
- Verify port number (7497 for paper, 7496 for live)
- Check firewall settings
- Verify API settings enabled

**"No executions found"**
- This is OK if you haven't traded recently
- Place a test paper trade and re-run
- Connection validation is still successful

### IBKR Greeks Issues

**"Greeks not available"**
- Check that you have market data subscription enabled
- Verify TWS/IB Gateway is running
- Try requesting Greeks for an active position first
- Some Greeks require real-time market data subscription

**"No positions found"**
- This is OK if you don't have options positions
- POC can still validate Greeks availability
- Place a test paper trade if needed

### Polygon Issues (Optional)

**"Invalid API key"**
- Verify API key in .env file
- Check for extra spaces or quotes
- Confirm subscription is active

**"403 Forbidden"**
- Your subscription doesn't include OPTIONS tier data
- Upgrade to OPTIONS subscription (~$99/month) or use IBKR for Greeks
- Run diagnostic: `python diagnose_polygon_subscription.py`

### General Issues

**"Module not found"**
```bash
# Reinstall requirements
pip install -r requirements-poc.txt
```

**"Permission denied"**
```bash
# On macOS/Linux, ensure scripts are executable
chmod +x poc_*.py
```

---

## Next Steps

### After POC Success

1. **Review Results** with development team
2. **Document any quirks** discovered during POCs
3. **Proceed to Phase 0**: Project setup & infrastructure
4. **Keep POC scripts** as reference during development

### Phase 0 Preview

Once POCs are validated, we'll build:
- Backend project scaffolding
- Docker Compose environment
- Database setup with PostgreSQL
- CI/CD pipeline with GitHub Actions
- Development tooling (Black, Ruff, pre-commit)
- CLI skeleton

**Estimated Time**: 3-5 days
**Timeline**: Days 4-8 of the project

---

## Questions or Issues?

If you encounter problems during POCs:

1. Check the troubleshooting section above
2. Review the detailed setup guides:
   - `IBKR_API_SETUP_GUIDE.md` for IBKR issues
   - Polygon documentation: https://polygon.io/docs
3. Verify all prerequisites are met
4. Double-check `.env` configuration

**Remember**: The whole point of POCs is to discover issues early! If something doesn't work, that's valuable information.

---

## POC Checklist

Use this checklist to track your progress:

- [ ] Python 3.11+ installed
- [ ] Virtual environment created and activated
- [ ] `requirements-poc.txt` installed
- [ ] `.env` file created with credentials
- [ ] **POC #1**: IBKR API access enabled
- [ ] **POC #1**: TWS/IB Gateway running
- [ ] **POC #1**: Connection test successful
- [ ] **POC #2**: IBKR Greeks fetching tested
- [ ] **POC #2**: All Greeks data validated (delta, gamma, theta, vega, IV)
- [ ] **POC #3**: Jupyter notebook running
- [ ] **POC #3**: Grouping algorithm tested
- [ ] All POC results documented
- [ ] GO/ADJUST/STOP decision made
- [ ] Ready to proceed to Phase 0

**Good luck with the POCs!** 🚀

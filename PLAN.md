# Trading Journal Development Plan

## Overview
This document tracks the development phases for the Trading Journal application, an options trading analytics platform.

---

## Phase 1: Core Foundation ✅ COMPLETED

### Database Models
- ✅ Execution model (individual fills from IBKR)
- ✅ Trade model (grouped executions)
- ✅ Base database setup with async SQLAlchemy

### Services
- ✅ IBKR service for fetching executions
- ✅ Execution service for storing and querying executions
- ✅ Trade grouping service with strategy classification

### API Endpoints
- ✅ Execution endpoints (fetch, list, get)
- ✅ Trade endpoints (process, list, get)

### CLI
- ✅ Basic CLI commands for data management

---

## Phase 2: Advanced Analytics & Position Tracking ✅ COMPLETED

### 1. Greeks Tracking System ✅
**Models:**
- ✅ Greeks model with delta, gamma, theta, vega, rho, IV
- ✅ Position model for tracking open positions

**Services:**
- ✅ `GreeksService` - Fetch and store Greeks from IBKR
- ✅ Historical Greeks tracking with timestamps
- ✅ Position-level Greeks aggregation

**API Endpoints:**
- ✅ `POST /api/v1/greeks/fetch` - Fetch Greeks for all positions
- ✅ `GET /api/v1/greeks/position/{id}/latest` - Get latest Greeks
- ✅ `GET /api/v1/greeks/position/{id}/history` - Get Greeks history

### 2. Position Management ✅
**Services:**
- ✅ `PositionService` - Sync positions from IBKR
- ✅ Real-time P&L calculation
- ✅ Support for stocks and options

**API Endpoints:**
- ✅ `POST /api/v1/positions/sync` - Sync positions from IBKR
- ✅ `GET /api/v1/positions` - List positions with filters
- ✅ `GET /api/v1/positions/{id}` - Get position details

### 3. Roll Detection ✅
**Services:**
- ✅ `RollDetectionService` - Intelligent roll detection
- ✅ Roll chain tracking and linking
- ✅ Roll statistics and analysis

**Features:**
- ✅ Time-based roll detection (24-hour window)
- ✅ Strategy similarity matching
- ✅ Execution overlap analysis
- ✅ Roll chain reconstruction

**API Endpoints:**
- ✅ `POST /api/v1/rolls/detect` - Detect and link rolls
- ✅ `GET /api/v1/rolls/chain/{trade_id}` - Get roll chain
- ✅ `GET /api/v1/rolls/statistics` - Roll statistics

### 4. Trade Analytics ✅
**Services:**
- ✅ `AnalyticsService` - Comprehensive trade statistics

**Features:**
- ✅ Win rate calculation with profit factor
- ✅ Strategy performance breakdown
- ✅ Underlying symbol analysis
- ✅ Monthly performance summaries
- ✅ Trade duration statistics

**API Endpoints:**
- ✅ `GET /api/v1/analytics/win-rate` - Win rate metrics
- ✅ `GET /api/v1/analytics/strategy-breakdown` - Strategy performance
- ✅ `GET /api/v1/analytics/underlying-breakdown` - Performance by symbol
- ✅ `GET /api/v1/analytics/monthly-performance` - Monthly stats
- ✅ `GET /api/v1/analytics/trade-duration` - Duration analysis

### 5. Performance Metrics ✅
**Services:**
- ✅ `PerformanceMetricsService` - Time-series and risk metrics

**Features:**
- ✅ Cumulative P&L time series
- ✅ Daily P&L aggregation
- ✅ Drawdown analysis (max and current)
- ✅ Sharpe ratio calculation
- ✅ Strategy-specific profit curves
- ✅ Equity curve summaries

**API Endpoints:**
- ✅ `GET /api/v1/performance/cumulative-pnl` - Equity curve data
- ✅ `GET /api/v1/performance/daily-pnl` - Daily aggregation
- ✅ `GET /api/v1/performance/drawdown` - Drawdown metrics
- ✅ `GET /api/v1/performance/sharpe-ratio` - Risk-adjusted returns
- ✅ `GET /api/v1/performance/strategy-curves` - Per-strategy curves
- ✅ `GET /api/v1/performance/equity-summary` - Summary statistics

### 6. Calendar Data Aggregation ✅
**Services:**
- ✅ `CalendarService` - Time-based data views

**Features:**
- ✅ Upcoming option expirations
- ✅ Trades grouped by week
- ✅ Calendar views (trades and expirations)
- ✅ Monthly summaries
- ✅ Day-of-week performance analysis

**API Endpoints:**
- ✅ `GET /api/v1/calendar/upcoming-expirations` - Expiration alerts
- ✅ `GET /api/v1/calendar/trades-by-week` - Weekly performance
- ✅ `GET /api/v1/calendar/trades-calendar` - Trade calendar view
- ✅ `GET /api/v1/calendar/expiration-calendar` - Expiration calendar
- ✅ `GET /api/v1/calendar/monthly-summary` - Month details
- ✅ `GET /api/v1/calendar/day-of-week-analysis` - Day patterns

### 7. Testing ✅
- ✅ Comprehensive test suite for all Phase 2 features
- ✅ 10 tests covering services and calculations
- ✅ 53% code coverage achieved
- ✅ All tests passing

---

## Phase 3: Frontend & Visualization ✅ COMPLETED

### Web Dashboard
- ✅ React/Next.js frontend (Next.js 16 with TypeScript)
- ✅ Interactive charts (equity curves, P&L, strategy breakdowns)
- ✅ Position management interface with IBKR sync
- ✅ Trade history with filtering (strategy, symbol, status)
- ✅ Analytics dashboards (win rate, strategy, underlying)

### Visualizations
- ✅ Equity curve charts (Recharts)
- ⏸️ Greeks heat maps (deferred to Phase 4)
- ✅ Strategy performance comparisons (bar charts)
- ✅ Calendar views with expirations
- ✅ Drawdown charts and metrics
- ✅ Win rate visualizations

### Pages Implemented
- ✅ Dashboard - Overview with key metrics
- ✅ Performance - Equity curve, Sharpe ratio, drawdown analysis
- ✅ Positions - Current positions table with sync capability
- ✅ Trades - Complete trade history with filters
- ✅ Analytics - Strategy and underlying breakdowns
- ✅ Calendar - Upcoming option expirations
- ✅ Settings - Configuration page

### Technical Stack
- ✅ Next.js 16 with App Router
- ✅ TypeScript for type safety
- ✅ Tailwind CSS for styling
- ✅ Recharts for data visualization
- ✅ API client with full backend integration
- ✅ Responsive design (mobile, tablet, desktop)

---

## Phase 4: Advanced Features (PLANNED)

### Automated Trading Integration
- [ ] Paper trading support
- [ ] Live trading capabilities
- [ ] Order management
- [ ] Position monitoring

### Machine Learning
- [ ] Pattern recognition in successful trades
- [ ] Strategy optimization suggestions
- [ ] Risk prediction models
- [ ] Entry/exit timing analysis

### Portfolio Management
- [ ] Multi-account support
- [ ] Portfolio-level Greeks aggregation
- [ ] Correlation analysis
- [ ] Risk management tools

---

## Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.13)
- **Database:** PostgreSQL with async SQLAlchemy
- **IBKR Integration:** ib_insync library
- **Testing:** pytest with async support

### Frontend
- **Framework:** Next.js 16 (React 19)
- **Language:** TypeScript
- **Styling:** Tailwind CSS 4
- **Charts:** Recharts
- **Icons:** Lucide React
- **State Management:** React Hooks
- **Data Fetching:** Native Fetch API

### Data Models
- Executions, Trades, Positions, Greeks
- Roll tracking and linking
- Time-series performance data

### API Design
- RESTful API with OpenAPI/Swagger docs
- Consistent response formats
- Comprehensive error handling
- Filter and pagination support

---

## Deployment (PLANNED)

### Infrastructure
- [ ] Docker containerization
- [ ] CI/CD pipeline
- [ ] Cloud deployment (AWS/GCP)
- [ ] Database migrations
- [ ] Monitoring and logging

---

## Phase 3.5: Data Import & Trade Management Improvements ✅ COMPLETED

**Completed:** December 5, 2024

### Flex Query Import System ✅
**Backend:**
- ✅ `FlexQueryParser` - CSV and XML format support
- ✅ File upload endpoint (`POST /api/v1/executions/upload`)
- ✅ Column mapping for IBKR Flex Query formats
- ✅ Database schema fix: INTEGER → BIGINT for order/perm IDs (handles values > 2.1B)
- ✅ Alembic migration for schema update

**Frontend:**
- ✅ File upload UI in Settings page
- ✅ Drag-and-drop or browse file upload
- ✅ Upload progress and result feedback
- ✅ Success/error message display
- ✅ Instructions for Flex Query configuration

**Fixes:**
- ✅ Fixed database overflow for large IBKR order IDs
- ✅ CSV parser field mapping corrections
- ✅ Proper handling of option symbols and multipliers

### Trade Display Improvements ✅
**Schema Alignment:**
- ✅ Fixed frontend/backend field name mismatches
  - `underlying_symbol` → `underlying`
  - `strategy` → `strategy_type`
  - Status values: lowercase → uppercase (`OPEN`, `CLOSED`)
- ✅ Updated API response handling (extract from wrapped `{trades: [...]}` format)
- ✅ Fixed data type conversions (Decimal to float for display)

**Data Quality Fixes:**
- ✅ Fixed unrealized P&L calculation for open positions
  - Changed from incorrect ledger calculation to $0.00 (requires live market data)
- ✅ Fixed total P&L to only show for closed trades
- ✅ Opening cost and closing proceeds now calculated correctly

**Trade Filtering & Deduplication:**
- ✅ Filter out position-sync trades (show only execution-based)
- ✅ SQL-based deduplication (keep most recent trade per underlying)
- ✅ Reduced 121 trades (73 stale + 48 duplicates) to 16 unique trades

### Execution Detail View ✅
**Backend:**
- ✅ New endpoint: `GET /api/v1/trades/{trade_id}/executions`
- ✅ Smart execution fetching by underlying and time range

**Frontend:**
- ✅ Expandable trade rows with chevron (▶/▼) buttons
- ✅ Detailed execution display showing:
  - BUY/SELL indicators (🟢/🔴)
  - Execution timestamp
  - Quantity and option details (strike, type, expiration)
  - Price, net amount, and commission
  - Individual execution breakdown
- ✅ Collapsible execution details for debugging strategy classification

**User Experience:**
- ✅ Click any trade to see constituent executions
- ✅ Verify strategy classification accuracy
- ✅ Debug trade grouping logic
- ✅ Understand position composition

### Trade Processing Improvements ✅
- ✅ Reprocessing support to fix existing trades
- ✅ Process Executions button on Trades page
- ✅ Real-time feedback on processing status
- ✅ Success/error messaging

---

## Phase 3.6: Trade Grouping Algorithm Redesign ✅ COMPLETED

**Completed:** December 9, 2024

### Problem Analysis
The original trade grouping algorithm had fundamental flaws:

1. **Time-Based Grouping Created Wrong Boundaries**
   - Grouped executions within 5-10 second windows
   - Couldn't distinguish between a single trade vs. a roll (close + open)
   - Example: Closing Dec spread and opening Jan spread within 5 seconds = 1 trade ❌ (should be 2)

2. **No Persistent Position State**
   - Each group processed in isolation with fresh ledger
   - Couldn't tell if SELL execution was closing a position or opening a short
   - Lost context between execution groups

3. **Single Trade Per Group Assumption**
   - Assumed each time-based group = one trade
   - Couldn't handle multiple trades within same time window (rolls)

4. **Insufficient Boundary Detection**
   - Used `is_flat()` but couldn't distinguish scenarios:
     - Opened and closed same position (1 trade) ✓
     - Closed old position, opened new (2 trades - roll) ❌

### Solution: Position State Machine

**Core Principle:** Track cumulative position state across ALL executions, detect trade boundaries when position structure changes.

**Key Improvements:**

1. **Persistent Position Tracking**
   - `cumulative_position: dict[leg_key, int]` maintained across all executions
   - Tracks net quantity for each unique option leg
   - Leg key format: `"YYYYMMDD_strike_type"` (e.g., `"20241220_140_C"`)

2. **Trade Boundary Detection**
   - Position goes FLAT → OPEN: Start new trade
   - Position goes OPEN → FLAT: Close current trade
   - Position structure changes (different legs): Close old trade, open new trade

3. **Multi-Leg Strategy Support**
   - Groups near-simultaneous executions (5-second window, same order_id)
   - Processes groups with position state machine
   - Detects: vertical spreads, butterflies, iron condors, etc.

4. **Roll Detection**
   - When leg structure changes completely (isdisjoint), identifies as roll
   - Closes old trade, opens new trade
   - Foundation for future roll linking

### Implementation Details

**New Methods in `TradeGroupingService`:**

- `_process_underlying_with_state_machine()` - Main state machine logic
- `_group_simultaneous_executions()` - Groups multi-leg orders
- `_get_leg_key_from_exec()` - Generates unique leg identifiers
- `_update_cumulative_position()` - Updates global position state
- `_trade_legs_are_flat()` - Checks if trade legs are at zero
- `_save_trade_from_ledger()` - Saves completed trades

**Algorithm Flow:**

```python
For each underlying:
    cumulative_position = {}  # Global state
    current_trade = None
    current_trade_legs = set()

    For each execution group (time-based):
        group_legs = get_legs_in_group()

        if no active trade:
            Start new trade with this group

        elif group_legs ⊆ current_trade_legs:
            Add to current trade
            if all trade legs flat:
                Close and save trade

        elif group_legs ∩ current_trade_legs = ∅:
            Different legs → Roll or new position
            Save current trade
            Start new trade

        else:
            Partial overlap → Adjustment
            Save current trade
            Start new trade
```

### Benefits

✅ **Accurate Trade Boundaries** - Detects when positions truly open/close
✅ **Roll Detection** - Identifies when old position closes and new opens
✅ **Persistent State** - Maintains context across all executions
✅ **Multi-Leg Support** - Correctly groups vertical spreads, butterflies, etc.
✅ **Simple & Maintainable** - Clear logic, easy to understand and debug

### Database Schema Updates

Added `extend_existing=True` to model table configurations to support hot-reloading:
- `src/trading_journal/models/execution.py`
- `src/trading_journal/models/trade.py`

## Current Status

**Phase 3.6 Completed:** December 9, 2024

All Phase 3, 3.5, and 3.6 features successfully implemented. The application now provides:

**Core Capabilities:**
- Complete full-stack trading journal application
- Backend: FastAPI with 45+ REST endpoints
- Frontend: Next.js 16 web dashboard with 7 pages
- Real-time data visualization and analytics
- IBKR integration (TWS sync + Flex Query import)
- Comprehensive trade tracking and performance metrics

**Recent Additions (Phase 3.5):**
- Flex Query CSV/XML import via file upload
- Database schema fixes for large IBKR IDs (BIGINT support)
- Corrected P&L calculations for open/closed positions
- Trade deduplication and filtering
- Expandable execution detail view
- Improved frontend/backend schema alignment

**Trade Data:**
- 204 executions imported from Flex Query
- 16 unique trades processed and displayed
- Support for Single, Vertical Spreads, and complex strategies
- Real-time execution breakdown for debugging

### Running the Application

**Backend:**
```bash
cd /Users/tommyk15/Documents/GitHub/trading-journal-cld
source venv/bin/activate
uvicorn src.trading_journal.main:app --reload
# Runs on http://localhost:8000
```

**Frontend:**
```bash
cd /Users/tommyk15/Documents/GitHub/trading-journal-cld/frontend
npm run dev
# Runs on http://localhost:3000
```

### Known Limitations

**Unrealized P&L:**
- Currently shows $0.00 for open positions
- Requires live market data integration for accurate values
- Closed positions show correct realized P&L

**Strategy Classification:**
- Basic pattern matching for common strategies
- May need refinement for complex multi-leg positions
- Execution detail view helps verify classification

**Next Steps:**
- Phase 4 enhancements (automated trading, ML features, deployment)
- Live market data integration for unrealized P&L
- Enhanced strategy classification algorithms

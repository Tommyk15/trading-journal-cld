# IBKR Flex Query Setup Guide

## Why Flex Query Instead of Live API?

The IBKR live API (`reqExecutions`) has major limitations:
- ❌ Only returns executions since midnight (same day)
- ❌ Maximum 1-2 days of history even with TWS settings adjusted
- ❌ Doesn't work with IB Gateway (only TWS)
- ❌ Requires specific TWS Trade Log settings

**Flex Query solves all of this:**
- ✅ Get up to 365 days of execution history
- ✅ Works with any account type
- ✅ No special API permissions needed
- ✅ More reliable for production systems
- ✅ This is what institutional traders use

---

## Step 1: Create a Flex Query in Account Management

### 1.1 Login to Account Management
1. Go to: https://www.interactivebrokers.com/portal
2. Login with your credentials
3. Navigate to: **Performance & Reports → Flex Queries**

### 1.2 Create New Flex Query
1. Click **"Create"** → **"Trade Confirmation Flex Query"**
2. Configure the query:

**Query Name:** `TradingJournalExecutions`

**Sections to Include:**
- ✅ **Trades** (this is the main section we need)
- ✅ **Execution** (detailed execution info)
- ✅ **Order** (order details)

**Fields to Include in Trades Section:**
```
Required Fields:
- Symbol
- Asset Category
- Date/Time
- Buy/Sell
- Quantity
- Price
- Proceeds
- Commission
- Basis
- Realized P/L
- Option Strike Price (for options)
- Option Expiry Date (for options)
- Put/Call (for options)
- Multiplier
- Trade ID
- Execution ID
- Order ID
```

**Date Range:**
- Select: **"Custom Date Range"**
- Default to: **Last 7 days** (you can adjust when downloading)

**Sort By:** Date/Time (Ascending)

**File Format:** CSV

### 1.3 Save and Note the Query ID
1. Click **"Save"**
2. You'll see your new query in the list
3. **Note the Query ID** (e.g., 123456)

---

## Step 2: Generate API Token

### 2.1 Create Flex Web Service Token
1. In Account Management, go to: **Settings → Account Settings**
2. Find: **Reporting** section
3. Look for: **Flex Web Service**
4. Click **"Generate Token"**
5. **Save this token securely** - you'll need it for the API

**Token format:** Usually looks like `123456789012345678901234567890123456`

---

## Step 3: Test the Flex Query

### 3.1 Using Web Interface (Quick Test)
1. Go to: **Performance & Reports → Flex Queries**
2. Find your query
3. Click **"Run"** next to your query
4. Select date range (e.g., Last 7 days)
5. Click **"Run"**
6. Download should start automatically
7. Open the CSV to verify your executions are there

### 3.2 Using API (What our POC will do)
The Flex Query API URL format:
```
https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest?
  t=<TOKEN>&
  q=<QUERY_ID>&
  v=3
```

---

## Step 4: Configure POC Script

Once you have:
1. ✅ Flex Query ID
2. ✅ Flex Web Service Token

Add them to your `.env` file:
```bash
# IBKR Flex Query (for historical executions)
IBKR_FLEX_TOKEN=your_flex_token_here
IBKR_FLEX_QUERY_ID=your_query_id_here
```

---

## Expected Timeline

- **Step 1-2**: 10-15 minutes (one-time setup)
- **Step 3**: 2 minutes (testing)
- **Step 4**: 1 minute (configuration)

**Total**: ~20 minutes one-time setup

---

## Advantages for Trading Journal

1. **Complete History**: Get all executions from the past year
2. **Reliable**: No midnight cutoff, no TWS settings to worry about
3. **Scheduled Updates**: Can run daily to fetch new executions
4. **No API Connection Issues**: Just HTTP requests, no socket connection
5. **Same Data**: Flex Query returns the same data you see in TWS Trade Log

---

## Next Steps

1. Follow Steps 1-3 above to set up your Flex Query
2. Get your Token and Query ID
3. Add them to `.env` file
4. Run the POC Flex Query script (we'll create this next)

---

## Troubleshooting

**"Cannot create Flex Query"**
- Ensure you're logged into Account Management, not TWS
- Check you have permissions for Flex Queries (usually enabled by default)

**"Token generation failed"**
- Contact IBKR support to enable Flex Web Service for your account
- This is usually enabled automatically for all accounts

**"Query returns no data"**
- Verify your date range includes your trades
- Check the query includes the "Trades" section
- Run the query manually in the web interface first

---

## References

- [IBKR Flex Query Documentation](https://www.interactivebrokers.com/en/software/am/am/reports/flex_queries.htm)
- [Flex Web Service API](https://www.interactivebrokers.com/en/software/am/am/reports/activityflexqueries.htm)

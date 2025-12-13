"""
POC #1: IBKR Connection & Execution Fetching

Goal:
- Connect to IBKR via official IBAPI
- Fetch executions from last 7 days from live account
- Print execution details to verify data structure

Validates:
- IBKR API credentials work
- Execution data is available
- We can access all needed fields
"""

import time
from datetime import datetime, timedelta
from threading import Thread
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.execution import ExecutionFilter


class IBKRClient(EWrapper, EClient):
    """
    IBKR API Client wrapper

    Combines EWrapper (handles callbacks) and EClient (sends requests)
    """

    def __init__(self):
        EClient.__init__(self, self)

        # Storage for executions
        self.executions = []
        self.execution_details = {}

        # Connection state
        self.next_valid_order_id = None
        self.connected = False
        self.account_code = None

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors from IBKR"""
        # Error 2104, 2106, 2158 are informational, not actual errors
        if errorCode in [2104, 2106, 2158]:
            return  # Don't print these, they're just connection status

        # Print all other errors
        print(f"❌ Error {errorCode}: {errorString}")

        # Check for permission-related errors
        if errorCode in [162, 200, 354, 10147]:
            print(f"   ⚠️  This looks like a PERMISSIONS issue!")
            print(f"   Check: Global Configuration → API → Settings")
            print(f"   Ensure 'Read-Only API' is DISABLED")

    def nextValidId(self, orderId: int):
        """
        Callback when connection is established
        IBKR sends this to confirm we're connected
        """
        print(f"✅ Connected to IBKR! Next valid order ID: {orderId}")
        self.next_valid_order_id = orderId
        self.connected = True

    def managedAccounts(self, accountsList: str):
        """
        Callback with list of managed accounts
        """
        print(f"📋 Managed Accounts: {accountsList}")
        # Take the first account as default
        accounts = accountsList.split(",")
        if accounts:
            self.account_code = accounts[0]
            print(f"📌 Using account: {self.account_code}")

    def execDetails(self, reqId, contract, execution):
        """
        Callback when execution details are received

        Args:
            reqId: Request ID we sent
            contract: Contract details (symbol, exchange, etc.)
            execution: Execution details (price, qty, time, etc.)
        """
        print(f"\n📊 Execution Received:")
        print(f"  Request ID: {reqId}")

        # Store execution
        exec_data = {
            'exec_id': execution.execId,
            'time': execution.time,
            'account': execution.acctNumber,
            'exchange': execution.exchange,
            'side': execution.side,
            'shares': execution.shares,
            'price': execution.price,
            'perm_id': execution.permId,
            'client_id': execution.clientId,
            'order_id': execution.orderId,
            'liquidation': execution.liquidation,
            'cum_qty': execution.cumQty,
            'avg_price': execution.avgPrice,

            # Contract details
            'symbol': contract.symbol,
            'sec_type': contract.secType,
            'currency': contract.currency,
            'local_symbol': contract.localSymbol,
        }

        # Add option-specific fields if it's an option
        if contract.secType == 'OPT':
            exec_data.update({
                'strike': contract.strike,
                'right': contract.right,  # 'C' or 'P'
                'expiry': contract.lastTradeDateOrContractMonth,
                'multiplier': contract.multiplier
            })

        self.executions.append(exec_data)

        # Print formatted execution
        print(f"  Exec ID: {execution.execId}")
        print(f"  Symbol: {contract.symbol} ({contract.secType})")
        print(f"  Side: {execution.side}")
        print(f"  Quantity: {execution.shares}")
        print(f"  Price: ${execution.price}")
        print(f"  Time: {execution.time}")

        if contract.secType == 'OPT':
            print(f"  Strike: ${contract.strike}")
            print(f"  Right: {contract.right}")
            print(f"  Expiry: {contract.lastTradeDateOrContractMonth}")

    def execDetailsEnd(self, reqId):
        """
        Callback when all executions have been received
        """
        print(f"\n✅ All executions received for request {reqId}")
        print(f"📈 Total executions: {len(self.executions)}")

    def commissionReport(self, commissionReport):
        """
        Callback for commission reports (optional)
        """
        print(f"\n💰 Commission Report:")
        print(f"  Exec ID: {commissionReport.execId}")
        print(f"  Commission: ${commissionReport.commission}")
        print(f"  Currency: {commissionReport.currency}")


def test_ibkr_connection(host='127.0.0.1', port=7496, client_id=0):
    """
    Test IBKR connection and fetch recent executions

    Args:
        host: IBKR host (default: localhost)
        port: IBKR port (7496 for live, 7497 for paper)
        client_id: Unique client ID for this connection

    Returns:
        List of execution dictionaries
    """
    print("=" * 80)
    print("POC #1: IBKR Connection & Execution Fetching")
    print("=" * 80)
    print(f"\n🔌 Connecting to IBKR...")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Client ID: {client_id}")
    print(f"\n⚠️  Make sure TWS or IB Gateway is running!")
    print("-" * 80)

    # Create client
    app = IBKRClient()

    # Connect to IBKR
    try:
        app.connect(host, port, client_id)
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Is TWS or IB Gateway running?")
        print("2. Are API settings enabled? (File → Global Configuration → API)")
        print("3. Is the port correct? (7497 for paper, 7496 for live)")
        print("4. Is localhost (127.0.0.1) allowed in API settings?")
        return []

    # Run the client in a separate thread
    # IBAPI requires a message loop to process callbacks
    api_thread = Thread(target=app.run, daemon=True)
    api_thread.start()

    # Wait for connection to establish
    timeout = 10
    start_time = time.time()
    while not app.connected and (time.time() - start_time) < timeout:
        time.sleep(0.1)

    if not app.connected:
        print(f"\n❌ Connection timeout after {timeout}s")
        app.disconnect()
        return []

    # Wait a bit more for account info to arrive
    print(f"\n⏳ Waiting for account information...")
    time.sleep(2)

    # Request executions (all executions for debugging)
    print(f"\n📥 Requesting all executions...")

    if app.account_code:
        print(f"   For account: {app.account_code}")

    # Create execution filter
    exec_filter = ExecutionFilter()

    # Try specifying the account if we have it
    if app.account_code:
        exec_filter.acctCode = app.account_code
        print(f"   Filtering by account: {app.account_code}")
    else:
        print(f"   ⚠️  No account code received - this might be the issue!")
        print(f"   Requesting executions for all accounts...")

    # Request executions
    request_id = 1
    app.reqExecutions(request_id, exec_filter)

    # Wait for executions to be received
    # Give it 10 seconds to receive data (increased for debugging)
    print("⏳ Waiting for execution data (10 seconds)...")
    time.sleep(10)

    # Disconnect
    print(f"\n🔌 Disconnecting from IBKR...")
    app.disconnect()

    # Summary
    print("\n" + "=" * 80)
    print("POC #1 RESULTS")
    print("=" * 80)
    print(f"\n✅ Successfully connected to IBKR")
    print(f"📊 Executions fetched: {len(app.executions)}")

    if app.executions:
        print(f"\n📋 Sample Execution (first one):")
        first_exec = app.executions[0]
        for key, value in first_exec.items():
            print(f"   {key}: {value}")

        print(f"\n🎯 Available Fields:")
        print(f"   {list(first_exec.keys())}")

        # Check for option executions
        option_execs = [e for e in app.executions if e['sec_type'] == 'OPT']
        print(f"\n📈 Option Executions: {len(option_execs)}")
        print(f"📈 Stock Executions: {len(app.executions) - len(option_execs)}")

        print(f"\n✅ POC #1 PASSED - IBKR connection works!")
    else:
        print(f"\n⚠️  No executions found in account")
        print(f"\n   Possible reasons:")
        print(f"   1. No trades have been executed on this account")
        print(f"   2. Wrong account connected (check account ID in TWS)")
        print(f"   3. Executions exist but API permissions issue")
        print(f"\n   Try:")
        print(f"   - Verify you're connected to the correct account in TWS")
        print(f"   - Check Account → Account ID in TWS")
        print(f"   - Place a test trade and re-run")
        print(f"\n✅ POC #1 PARTIAL - Connection works, but no data to verify")

    print("=" * 80)

    return app.executions


if __name__ == "__main__":
    # Configuration
    # Change these based on your setup
    HOST = '127.0.0.1'  # localhost
    PORT = 7496         # 7496 for live trading, 7497 for paper
    CLIENT_ID = 1       # Unique ID for this connection

    # Run the test
    executions = test_ibkr_connection(HOST, PORT, CLIENT_ID)

    # Print summary
    if executions:
        print(f"\n✅ SUCCESS: Retrieved {len(executions)} executions")
        print(f"\nNext steps:")
        print(f"1. ✅ IBKR connection works")
        print(f"2. ✅ Can fetch execution data")
        print(f"3. ⏭️  Move to POC #2 (Polygon.io)")
    else:
        print(f"\n⚠️  No executions retrieved")
        print(f"\nNext steps:")
        print(f"1. Place a test trade in TWS (paper trading)")
        print(f"2. Re-run this script")
        print(f"3. If connection works but no data, that's OK - connection is validated")

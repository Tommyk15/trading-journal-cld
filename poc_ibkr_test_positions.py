"""
IBKR API Diagnostic - Test if we can access other account data

This script tests if the API can access positions and account values.
If this works but executions don't, it's a specific permissions issue.
"""

import time
from threading import Thread
from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class DiagnosticClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.positions = []
        self.account_values = []
        self.connected = False
        self.account_code = None

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode not in [2104, 2106, 2158]:
            print(f"Error {errorCode}: {errorString}")

    def nextValidId(self, orderId: int):
        print(f"✅ Connected to IBKR!")
        self.connected = True

    def managedAccounts(self, accountsList: str):
        print(f"📋 Account: {accountsList}")
        accounts = accountsList.split(",")
        if accounts:
            self.account_code = accounts[0]

    def position(self, account, contract, position, avgCost):
        """Callback for position data"""
        print(f"📊 Position: {contract.symbol} ({contract.secType}) - Qty: {position} @ ${avgCost}")
        self.positions.append({
            'symbol': contract.symbol,
            'type': contract.secType,
            'quantity': position,
            'avg_cost': avgCost
        })

    def positionEnd(self):
        """Called when all positions received"""
        print(f"\n✅ All positions received: {len(self.positions)} total")

    def updateAccountValue(self, key, val, currency, accountName):
        """Callback for account values"""
        if key in ['NetLiquidation', 'TotalCashValue', 'GrossPositionValue']:
            print(f"💰 {key}: {val} {currency}")
            self.account_values.append({
                'key': key,
                'value': val,
                'currency': currency
            })

    def accountDownloadEnd(self, accountName):
        """Called when account data download is complete"""
        print(f"\n✅ Account data download complete")


def test_api_access():
    """Test what data the API can access"""
    print("=" * 80)
    print("IBKR API DIAGNOSTIC TEST")
    print("=" * 80)
    print("\nTesting if API can access:")
    print("  1. Positions")
    print("  2. Account values")
    print("\nIf these work but executions don't, it's a permissions issue.\n")
    print("-" * 80)

    app = DiagnosticClient()

    # Connect
    try:
        app.connect('127.0.0.1', 7496, 1)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return

    # Start thread
    api_thread = Thread(target=app.run, daemon=True)
    api_thread.start()

    # Wait for connection
    timeout = 10
    start_time = time.time()
    while not app.connected and (time.time() - start_time) < timeout:
        time.sleep(0.1)

    if not app.connected:
        print("❌ Connection timeout")
        app.disconnect()
        return

    time.sleep(2)

    # Request positions
    print("\n📥 Requesting positions...")
    app.reqPositions()

    # Request account updates
    if app.account_code:
        print(f"📥 Requesting account values for {app.account_code}...")
        app.reqAccountUpdates(True, app.account_code)

    # Wait for data
    print("\n⏳ Waiting for data (10 seconds)...\n")
    time.sleep(10)

    # Stop account updates
    if app.account_code:
        app.reqAccountUpdates(False, app.account_code)

    # Disconnect
    app.disconnect()

    # Results
    print("\n" + "=" * 80)
    print("DIAGNOSTIC RESULTS")
    print("=" * 80)

    if app.positions or app.account_values:
        print("\n✅ SUCCESS: API can access account data!")
        print(f"\nPositions received: {len(app.positions)}")
        print(f"Account values received: {len(app.account_values)}")
        print("\n⚠️  Since we CAN access positions but NOT executions:")
        print("   This is a SPECIFIC PERMISSION issue with execution data.")
        print("\n📝 Solutions:")
        print("   1. Check TWS: File → Global Config → API → Settings")
        print("      - Ensure 'Read-Only API' is UNCHECKED")
        print("   2. Check IBKR Account Management (web portal):")
        print("      - Settings → Trading Permissions")
        print("      - Look for API execution data restrictions")
        print("   3. Contact IBKR support about 'API execution data access'")
    else:
        print("\n❌ FAILURE: Cannot access ANY account data via API")
        print("\n📝 This suggests a broader API permissions issue:")
        print("   1. Verify API is enabled in Account Management (web)")
        print("   2. Check for account-level API restrictions")
        print("   3. Ensure account is fully approved for API trading")

    print("=" * 80)


if __name__ == "__main__":
    test_api_access()

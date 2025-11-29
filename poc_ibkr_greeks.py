"""
POC #2: IBKR Greeks Fetching

Goal:
- Connect to IBKR via official IBAPI
- Fetch Greeks for option positions (delta, gamma, theta, vega, IV)
- Verify all needed Greeks are available

Validates:
- IBKR API provides Greeks data
- Greeks data structure is as expected
- Can fetch Greeks for actual positions or test contracts
"""

import os
import time
from threading import Thread
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from dotenv import load_dotenv


class GreeksClient(EWrapper, EClient):
    """
    IBKR client for fetching Greeks data
    """

    def __init__(self):
        EClient.__init__(self, self)
        self.connected = False
        self.positions = []
        self.greeks_data = {}
        self.data_received = {}
        self.req_id_counter = 1000

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors from IBKR"""
        # Ignore informational messages
        if errorCode not in [2104, 2106, 2158, 2119]:
            print(f"   ⚠️  Error {errorCode} (reqId {reqId}): {errorString}")

    def nextValidId(self, orderId: int):
        """Called when connection is established"""
        print(f"✅ Connected to IBKR!")
        self.connected = True

    def position(self, account, contract, position, avgCost):
        """Callback for position data"""
        if contract.secType == "OPT":
            print(f"   Found option: {contract.symbol} {contract.lastTradeDateOrContractMonth} "
                  f"{contract.right} ${contract.strike}")
            # Ensure exchange is set for market data requests
            if not contract.exchange:
                contract.exchange = "SMART"
            if not contract.currency:
                contract.currency = "USD"
            self.positions.append(contract)

    def positionEnd(self):
        """Called when all positions received"""
        print(f"✅ Received {len(self.positions)} option positions\n")

    def tickOptionComputation(self, reqId, tickType, tickAttrib,
                            impliedVol, delta, optPrice, pvDividend,
                            gamma, vega, theta, undPrice):
        """
        Callback for option Greeks and implied volatility

        tickType values:
        - 10: Bid option computation
        - 11: Ask option computation
        - 12: Last option computation
        - 13: Model option computation (most complete)
        """
        # Store data from any tick type (not just 13)
        # We'll use the most complete data available
        if reqId not in self.greeks_data or tickType == 13:
            self.greeks_data[reqId] = {
                'delta': delta,
                'gamma': gamma,
                'theta': theta,
                'vega': vega,
                'implied_vol': impliedVol,
                'option_price': optPrice,
                'underlying_price': undPrice,
                'tick_type': tickType
            }
            self.data_received[reqId] = True
            print(f"   ✓ Greeks received for reqId {reqId} (tickType {tickType})")

    def tickPrice(self, reqId, tickType, price, attrib):
        """Handle price ticks (for market data)"""
        pass  # We primarily care about Greeks, not regular price ticks


def create_test_contract():
    """
    Create a test SPY option contract for validation
    Returns a Contract object for a near-dated SPY call
    """
    contract = Contract()
    contract.symbol = "SPY"
    contract.secType = "OPT"
    contract.exchange = "SMART"
    contract.currency = "USD"
    contract.lastTradeDateOrContractMonth = "20260102"  # Jan 2026
    contract.strike = 685.0
    contract.right = "C"  # Call
    contract.multiplier = "100"
    return contract


def validate_greeks(greeks_data):
    """
    Validate that all required Greeks are present

    Args:
        greeks_data: Dictionary with Greeks values

    Returns:
        Dictionary with validation results
    """
    results = {
        'valid': False,
        'missing_fields': [],
        'greeks': {}
    }

    if not greeks_data:
        results['missing_fields'].append('no greeks data received')
        return results

    # Required Greeks fields
    required_greeks = {
        'delta': 'Delta (Δ) - Price sensitivity',
        'gamma': 'Gamma (Γ) - Delta sensitivity',
        'theta': 'Theta (Θ) - Time decay',
        'vega': 'Vega - IV sensitivity',
        'implied_vol': 'Implied Volatility (IV)'
    }

    # Check each Greek (IBKR uses very large negative numbers for unavailable data)
    for greek_name, description in required_greeks.items():
        value = greeks_data.get(greek_name)

        # Check if value is valid (not None and not IBKR's "unavailable" marker)
        if value is not None and value > -9e37:
            results['greeks'][greek_name] = value

            # Format output based on Greek type
            if greek_name == 'implied_vol':
                print(f"   ✅ {description}: {value * 100:.2f}%")
            elif greek_name == 'theta':
                print(f"   ✅ {description}: {value:.4f} per day")
            else:
                print(f"   ✅ {description}: {value:.4f}")
        else:
            results['missing_fields'].append(greek_name)
            print(f"   ❌ Missing: {description}")

    # Show additional data
    if greeks_data.get('option_price') and greeks_data['option_price'] > 0:
        print(f"   ℹ️  Option Price: ${greeks_data['option_price']:.2f}")
    if greeks_data.get('underlying_price') and greeks_data['underlying_price'] > 0:
        print(f"   ℹ️  Underlying Price: ${greeks_data['underlying_price']:.2f}")

    # Validation result
    results['valid'] = len(results['missing_fields']) == 0

    return results


def test_ibkr_greeks():
    """
    Test IBKR Greeks fetching

    Returns:
        Validation results dictionary
    """
    print("=" * 80)
    print("POC #2: IBKR Greeks Fetching")
    print("=" * 80)

    # Load environment
    load_dotenv()
    port = int(os.getenv("IBKR_PORT", 7496))
    client_id = int(os.getenv("IBKR_CLIENT_ID", 1))

    # Create client
    app = GreeksClient()

    # Connect
    print(f"\n🔌 Connecting to IBKR (port {port})...")
    try:
        app.connect('127.0.0.1', port, client_id)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Is TWS or IB Gateway running?")
        print("  2. Is the correct port configured? (7496 live, 7497 paper)")
        print("  3. Are API settings enabled?")
        return {'valid': False, 'missing_fields': ['connection_failed']}

    # Start API thread
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
        return {'valid': False, 'missing_fields': ['connection_timeout']}

    time.sleep(1)

    # Try to fetch positions first
    print(f"\n📊 Fetching option positions...")
    app.reqPositions()
    time.sleep(3)

    # Decide which contract to test
    if app.positions:
        print(f"\n🎯 Testing Greeks for your positions:")
        test_contracts = app.positions[:3]  # Test up to 3 positions
    else:
        print(f"\n⚠️  No option positions found")
        print(f"🎯 Testing with SPY test contract instead:")
        test_contracts = [create_test_contract()]
        test_contract = test_contracts[0]
        print(f"   {test_contract.symbol} {test_contract.lastTradeDateOrContractMonth} "
              f"{test_contract.right} ${test_contract.strike}")

    # Request Greeks for contracts
    print(f"\n📥 Requesting Greeks data...\n")
    req_ids = []
    for i, contract in enumerate(test_contracts):
        req_id = app.req_id_counter + i
        req_ids.append(req_id)

        # Request market data with Greeks (genericTickList="106" requests Greeks)
        app.reqMktData(req_id, contract, "106", False, False, [])
        app.data_received[req_id] = False

    # Wait for Greeks data
    print(f"⏳ Waiting for Greeks data (20 seconds)...\n")
    time.sleep(20)

    # Cancel market data subscriptions
    for req_id in req_ids:
        app.cancelMktData(req_id)

    # Disconnect
    app.disconnect()
    time.sleep(1)

    # Validate results
    print("\n" + "=" * 80)
    print("POC #2 RESULTS")
    print("=" * 80)

    # Check if we got any Greeks data
    if not app.greeks_data:
        print("\n❌ POC #2 FAILED - No Greeks data received!")
        print("\n🔍 Troubleshooting:")
        print("   1. Do you have market data subscription for options?")
        print("   2. Try during market hours (9:30 AM - 4:00 PM ET)")
        print("   3. Check TWS market data subscriptions")
        print("   4. Verify the option contract is valid and liquid")
        return {'valid': False, 'missing_fields': ['no_data_received']}

    # Validate Greeks for first contract that returned data
    validation = None
    for req_id, greeks in app.greeks_data.items():
        contract_idx = req_ids.index(req_id)
        contract = test_contracts[contract_idx]

        print(f"\n📊 Contract: {contract.symbol} {contract.lastTradeDateOrContractMonth} "
              f"{contract.right} ${contract.strike}")
        print(f"\n🔍 Validating Greeks data...")

        validation = validate_greeks(greeks)

        if validation['valid']:
            print(f"\n✅ POC #2 PASSED - All required Greeks are available!")
            print(f"\n🎯 Next Steps:")
            print(f"   1. ✅ IBKR connection works")
            print(f"   2. ✅ All Greeks data available")
            print(f"   3. ⏭️  Move to POC #3 (Grouping Algorithm)")
            break
        else:
            # Try next contract if available
            if contract_idx < len(test_contracts) - 1:
                print(f"\n⚠️  Some Greeks missing, trying next contract...")
                continue

    # If no valid Greeks found
    if not validation or not validation['valid']:
        print(f"\n⚠️  POC #2 PARTIAL - Connection works, but Greeks incomplete")
        print(f"\n⚠️  Missing Fields:")
        for field in validation['missing_fields']:
            print(f"   - {field}")

        print(f"\n💡 Possible Solutions:")
        print(f"   1. Verify market data subscription includes options Greeks")
        print(f"   2. Try during market hours for live data")
        print(f"   3. Check if contract is actively traded")
        print(f"   4. Contact IBKR support about Greeks data access")

        if validation['greeks']:
            print(f"\n📊 Available Greeks:")
            for greek, value in validation['greeks'].items():
                print(f"   {greek}: {value}")

    print("=" * 80)

    return validation


if __name__ == "__main__":
    # Run the test
    validation = test_ibkr_greeks()

    # Exit with appropriate code
    if validation and validation['valid']:
        print("\n✅ SUCCESS: IBKR provides all required Greeks data")
        exit(0)
    elif validation and validation.get('greeks'):
        print("\n⚠️  PARTIAL SUCCESS: IBKR connection works, some Greeks available")
        print("   Check market data subscription for full Greeks access")
        exit(0)  # Exit successfully - connection works
    else:
        print("\n❌ FAILURE: Could not fetch Greeks data from IBKR")
        print("   Check connection, market data subscription, and contract validity")
        exit(1)

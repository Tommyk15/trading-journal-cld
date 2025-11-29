"""
IBKR API Test - Try reqCompletedOrders instead of reqExecutions

Some IBKR accounts can access completed orders but not raw executions.
This tests if we can get trade data via the orders API instead.
"""

import time
from threading import Thread
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.order import Order


class OrderTestClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.orders = []
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

    def completedOrder(self, contract, order, orderState):
        """Callback for completed orders"""
        print(f"\n📊 Completed Order:")
        print(f"   Order ID: {order.orderId}")
        print(f"   Symbol: {contract.symbol} ({contract.secType})")
        print(f"   Action: {order.action}")
        print(f"   Quantity: {order.totalQuantity}")
        print(f"   Status: {orderState.status}")

        if contract.secType == 'OPT':
            print(f"   Strike: ${contract.strike}")
            print(f"   Right: {contract.right}")
            print(f"   Expiry: {contract.lastTradeDateOrContractMonth}")

        self.orders.append({
            'order_id': order.orderId,
            'symbol': contract.symbol,
            'sec_type': contract.secType,
            'action': order.action,
            'quantity': order.totalQuantity,
            'status': orderState.status
        })

    def completedOrdersEnd(self):
        """Called when all completed orders received"""
        print(f"\n✅ All completed orders received: {len(self.orders)} total")


def test_completed_orders():
    """Test if we can access completed orders"""
    print("=" * 80)
    print("IBKR API TEST - Completed Orders")
    print("=" * 80)
    print("\nTrying reqCompletedOrders() instead of reqExecutions()")
    print("This might work even if executions don't.\n")
    print("-" * 80)

    app = OrderTestClient()

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

    # Request completed orders
    print("\n📥 Requesting completed orders...")
    app.reqCompletedOrders(False)  # False = include all orders, not just API orders

    # Wait for data
    print("⏳ Waiting for order data (15 seconds)...\n")
    time.sleep(15)

    # Disconnect
    app.disconnect()

    # Results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    if app.orders:
        print(f"\n✅ SUCCESS: Retrieved {len(app.orders)} completed orders!")
        print(f"\n📊 Order breakdown:")

        opt_orders = [o for o in app.orders if o['sec_type'] == 'OPT']
        stk_orders = [o for o in app.orders if o['sec_type'] == 'STK']

        print(f"   Option orders: {len(opt_orders)}")
        print(f"   Stock orders: {len(stk_orders)}")

        print(f"\n🎯 NEXT STEP:")
        print(f"   We can use reqCompletedOrders() to get trade data!")
        print(f"   This will work for the trading journal.")
    else:
        print(f"\n❌ No completed orders retrieved.")
        print(f"\n📝 This means:")
        print(f"   - Both reqExecutions() and reqCompletedOrders() are blocked")
        print(f"   - Need to use alternative approach (Flex Query or manual export)")

    print("=" * 80)


if __name__ == "__main__":
    test_completed_orders()

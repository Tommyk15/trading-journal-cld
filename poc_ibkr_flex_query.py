"""
POC #1 Alternative: IBKR Flex Query Execution Fetching

This is the CORRECT way to get historical execution data from IBKR.
The live API (reqExecutions) only works for same-day trades.

Flex Query advantages:
- Get up to 365 days of execution history
- No midnight cutoff limitation
- No special API permissions needed
- More reliable for production
"""

import os
import requests
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv


def request_flex_report(token, query_id):
    """
    Step 1: Request the Flex Report
    Returns a reference code to check status
    """
    print("📥 Requesting Flex Report from IBKR...")

    url = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
    params = {
        't': token,
        'q': query_id,
        'v': '3'
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        # Parse XML response
        root = ET.fromstring(response.content)

        status = root.find('.//Status').text
        if status == 'Success':
            reference_code = root.find('.//ReferenceCode').text
            print(f"✅ Report requested successfully")
            print(f"   Reference Code: {reference_code}")
            return reference_code
        else:
            error_code = root.find('.//ErrorCode').text
            error_msg = root.find('.//ErrorMessage').text
            print(f"❌ Error: {error_code} - {error_msg}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None
    except ET.ParseError as e:
        print(f"❌ Failed to parse response: {e}")
        return None


def fetch_flex_report(token, reference_code, max_retries=30):
    """
    Step 2: Fetch the Flex Report using reference code
    May need to retry as report generation takes time
    """
    print(f"\n📊 Fetching Flex Report...")
    print(f"   (Large reports can take 1-2 minutes to generate)\n")

    url = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
    params = {
        't': token,
        'q': reference_code,
        'v': '3'
    }

    for attempt in range(max_retries):
        try:
            print(f"   Attempt {attempt + 1}/{max_retries}...", end=' ')
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Debug: Check response content type
            content_preview = response.content[:100]

            # Check if we got XML (success) or still processing
            if response.content.startswith(b'<?xml'):
                root = ET.fromstring(response.content)

                # Check for error status
                status = root.find('.//Status')
                if status is not None and status.text != 'Success':
                    error_code = root.find('.//ErrorCode')
                    error_msg = root.find('.//ErrorMessage')
                    if error_code is not None:
                        print(f"\n❌ Error: {error_code.text} - {error_msg.text}")
                        return None

                # Check if it's a statement not ready response
                if b'Statement generation in progress' in response.content or b'Statement is being generated' in response.content:
                    print("Still generating...")
                    time.sleep(5)
                    continue

                # Success - we have the report
                print("✅ Report ready!")
                return root
            else:
                # Still processing (might be plain text response)
                response_text = response.text[:200]
                if 'Statement generation in progress' in response_text or 'is being generated' in response_text:
                    print("Generating...")
                    time.sleep(5)
                else:
                    print(f"Processing... (Response: {response_text[:50]})")
                    time.sleep(5)

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Request failed: {e}")
            return None
        except ET.ParseError as e:
            # Not XML yet, still processing
            print(f"Waiting... (Not XML yet)")
            time.sleep(5)

    print(f"\n❌ Report not ready after {max_retries} attempts (~{max_retries * 5 // 60} minutes)")
    print(f"\n💡 Possible issues:")
    print(f"   1. Report is very large (many executions)")
    print(f"   2. IBKR servers are slow")
    print(f"   3. Query configuration issue")
    print(f"\n   Try running the query manually in Account Management to verify it works")
    return None


def parse_executions(report_xml):
    """
    Parse executions from Flex Report XML
    """
    executions = []

    # Find all Trade elements
    trades = report_xml.findall('.//Trade')

    print(f"\n📋 Parsing executions from Flex Report...")
    print(f"   Found {len(trades)} trade records")

    for trade in trades:
        execution = {
            'symbol': trade.get('symbol'),
            'asset_type': trade.get('assetCategory'),
            'date_time': trade.get('dateTime'),
            'side': trade.get('buySell'),  # 'BUY' or 'SELL'
            'quantity': float(trade.get('quantity', 0)),
            'price': float(trade.get('tradePrice', 0)),
            'proceeds': float(trade.get('proceeds', 0)),
            'commission': float(trade.get('ibCommission', 0)),
            'realized_pnl': float(trade.get('fifoPnlRealized', 0)) if trade.get('fifoPnlRealized') else None,
            'trade_id': trade.get('tradeID'),
            'exec_id': trade.get('ibExecID'),
            'order_id': trade.get('ibOrderID'),
        }

        # Add option-specific fields
        if execution['asset_type'] == 'OPT':
            execution['strike'] = float(trade.get('strike', 0))
            execution['expiry'] = trade.get('expiry')
            execution['right'] = trade.get('putCall')  # 'P' or 'C'
            execution['multiplier'] = float(trade.get('multiplier', 100))

        executions.append(execution)

    return executions


def test_flex_query(token, query_id):
    """
    Test IBKR Flex Query execution fetching
    """
    print("=" * 80)
    print("POC #1 (Flex Query): IBKR Execution Fetching")
    print("=" * 80)
    print("\nUsing Flex Query API (the correct way for historical data)")
    print("-" * 80)

    # Step 1: Request the report
    reference_code = request_flex_report(token, query_id)
    if not reference_code:
        print("\n❌ Failed to request report")
        return []

    # Step 2: Fetch the report (with retries)
    report_xml = fetch_flex_report(token, reference_code)
    if report_xml is None:
        print("\n❌ Failed to fetch report")
        return []

    # Step 3: Parse executions
    executions = parse_executions(report_xml)

    # Results
    print("\n" + "=" * 80)
    print("POC #1 RESULTS (Flex Query)")
    print("=" * 80)

    if executions:
        print(f"\n✅ SUCCESS: Retrieved {len(executions)} executions!")

        # Show first few executions
        print(f"\n📊 Sample Executions (first 5):")
        for i, exec in enumerate(executions[:5], 1):
            print(f"\n{i}. {exec['symbol']} ({exec['asset_type']})")
            print(f"   Date: {exec['date_time']}")
            print(f"   {exec['side']} {exec['quantity']} @ ${exec['price']}")
            if exec['asset_type'] == 'OPT':
                print(f"   Strike: ${exec['strike']} {exec['right']} Exp: {exec['expiry']}")
            print(f"   Commission: ${exec['commission']}")
            print(f"   Trade ID: {exec['trade_id']}")

        # Summary stats
        option_execs = [e for e in executions if e['asset_type'] == 'OPT']
        stock_execs = [e for e in executions if e['asset_type'] == 'STK']

        print(f"\n📈 Summary:")
        print(f"   Total executions: {len(executions)}")
        print(f"   Option executions: {len(option_execs)}")
        print(f"   Stock executions: {len(stock_execs)}")

        print(f"\n✅ POC #1 PASSED - Flex Query works perfectly!")
        print(f"\n🎯 Next Steps:")
        print(f"   1. ✅ We can fetch historical execution data")
        print(f"   2. ✅ All required fields are available")
        print(f"   3. ⏭️  Move to POC #2 (Polygon.io Greeks)")

    else:
        print(f"\n⚠️  No executions found in Flex Query")
        print(f"\n   Possible reasons:")
        print(f"   1. Date range in Flex Query doesn't include your trades")
        print(f"   2. Query not configured correctly")
        print(f"   3. No trades in the selected period")
        print(f"\n   Try:")
        print(f"   - Run the query manually in IBKR Account Management")
        print(f"   - Adjust the date range in the Flex Query settings")

    print("=" * 80)
    return executions


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    token = os.getenv("IBKR_FLEX_TOKEN")
    query_id = os.getenv("IBKR_FLEX_QUERY_ID")

    if not token or not query_id:
        print("❌ ERROR: Missing Flex Query credentials")
        print("\nPlease follow these steps:")
        print("\n1. Read: FLEX_QUERY_SETUP.md")
        print("2. Create a Flex Query in IBKR Account Management")
        print("3. Generate a Flex Web Service Token")
        print("4. Add to .env file:")
        print("   IBKR_FLEX_TOKEN=your_token_here")
        print("   IBKR_FLEX_QUERY_ID=your_query_id_here")
        print("\n📖 See FLEX_QUERY_SETUP.md for detailed instructions")
        exit(1)

    # Run the test
    executions = test_flex_query(token, query_id)

    if executions:
        print(f"\n✅ SUCCESS: Flex Query is the solution for historical execution data!")
        print(f"\nWe'll use this approach for the full trading journal.")
    else:
        print(f"\n📝 Review the Flex Query setup and try again")

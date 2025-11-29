"""
POC #2: Polygon.io Options Data Fetching

Goal:
- Connect to Polygon.io API
- Fetch option data (attempts Greeks if available, falls back to contract details)
- Verify option data availability

Validates:
- Polygon.io API key works
- Options data is available (Greeks require OPTIONS subscription tier)
- Data structure is as expected

Note: Greeks data requires Polygon.io OPTIONS tier subscription (~$99/month)
      This POC will work with STARTER+ tier using contract details endpoint
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv


class PolygonGreeksValidator:
    """
    Polygon.io API client for validating Greeks data availability
    """

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"

    def get_option_contract(self, underlying="SPY", days_to_expiry=30, strike_offset=0):
        """
        Get an option contract ticker for testing

        Args:
            underlying: Underlying symbol (default: SPY)
            days_to_expiry: Target days to expiration (default: 30)
            strike_offset: Offset from current price (0 = ATM)

        Returns:
            Option ticker string (e.g., "O:SPY250117C00590000")
        """
        print(f"\n🔍 Finding option contract for {underlying}...")

        # Get current price of underlying
        url = f"{self.base_url}/v2/aggs/ticker/{underlying}/prev"
        params = {"apiKey": self.api_key}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("results"):
                current_price = data["results"][0]["c"]
                print(f"   Current {underlying} price: ${current_price:.2f}")
            else:
                print(f"   ⚠️  Could not get {underlying} price, using $590 as default")
                current_price = 590.0

        except Exception as e:
            print(f"   ⚠️  Error getting price: {e}")
            current_price = 590.0

        # Calculate target expiration date
        target_date = datetime.now() + timedelta(days=days_to_expiry)

        # Find the next Friday (standard monthly expiration)
        days_ahead = 4 - target_date.weekday()  # Friday is 4
        if days_ahead <= 0:
            days_ahead += 7
        expiry_date = target_date + timedelta(days=days_ahead)

        # Format expiration as YYMMDD
        expiry_str = expiry_date.strftime("%y%m%d")

        # Calculate strike (round to nearest $5 for SPY, adjust for other underlyings)
        strike = round(current_price / 5) * 5 + strike_offset
        strike_str = f"{int(strike * 1000):08d}"

        # Build option ticker (Polygon format)
        # Format: O:UNDERLYING + YYMMDD + C/P + STRIKE*1000
        option_ticker = f"O:{underlying}{expiry_str}C{strike_str}"

        print(f"   Generated option ticker: {option_ticker}")
        print(f"   Expiry: {expiry_date.strftime('%Y-%m-%d')} (~{days_to_expiry} days)")
        print(f"   Strike: ${strike}")
        print(f"   Type: Call")

        return option_ticker

    def get_option_snapshot(self, option_ticker):
        """
        Fetch option snapshot with Greeks from Polygon.io
        Falls back to contract details if snapshot is unavailable

        Args:
            option_ticker: Option ticker (e.g., "O:SPY250117C00590000")

        Returns:
            Dictionary with data or None if failed
        """
        print(f"\n📊 Fetching option data from Polygon.io...")
        print(f"   Ticker: {option_ticker}")

        # Try snapshot endpoint first (includes Greeks)
        url = f"{self.base_url}/v3/snapshot/options/{option_ticker}"
        params = {"apiKey": self.api_key}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                print(f"   ✅ Snapshot retrieved successfully (includes Greeks)")
                return {"source": "snapshot", "data": data["results"]}
            else:
                print(f"   ❌ No data returned")
                return None

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                print(f"   ⚠️  Snapshot endpoint requires OPTIONS subscription (403)")
                print(f"   ℹ️  Falling back to contract details endpoint...")
                return self.get_option_contract_details(option_ticker)
            elif e.response.status_code == 404:
                print(f"   ❌ Option contract not found (404)")
                print(f"   This might happen if:")
                print(f"      - The contract doesn't exist")
                print(f"      - The expiration date has passed")
                print(f"      - The ticker format is incorrect")
                return None
            else:
                print(f"   ❌ HTTP Error {e.response.status_code}: {e}")
                return None

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return None

    def get_option_contract_details(self, option_ticker):
        """
        Fetch option contract details (fallback when snapshot unavailable)

        Args:
            option_ticker: Option ticker (e.g., "O:SPY250117C00590000")

        Returns:
            Dictionary with contract data or None if failed
        """
        url = f"{self.base_url}/v3/reference/options/contracts/{option_ticker}"
        params = {"apiKey": self.api_key}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                print(f"   ✅ Contract details retrieved")
                print(f"   ⚠️  Note: Contract details do NOT include Greeks/IV")
                return {"source": "contract", "data": data["results"]}
            else:
                print(f"   ❌ No contract data returned")
                return None

        except Exception as e:
            print(f"   ❌ Error fetching contract details: {e}")
            return None

    def validate_greeks(self, response):
        """
        Validate data from Polygon (either snapshot with Greeks or contract details)

        Args:
            response: Response dict with 'source' and 'data' keys

        Returns:
            Dictionary with validation results
        """
        results = {
            'valid': False,
            'source': None,
            'missing_fields': [],
            'greeks': {},
            'contract_details': {},
            'details': {}
        }

        if not response:
            results['missing_fields'].append('response is None')
            return results

        source = response.get('source')
        data = response.get('data')
        results['source'] = source

        print(f"\n🔍 Validating data from {source} endpoint...")

        if source == 'snapshot':
            # Validate snapshot data (includes Greeks)
            return self._validate_snapshot_data(data, results)
        elif source == 'contract':
            # Validate contract data (no Greeks, but has contract details)
            return self._validate_contract_data(data, results)
        else:
            results['missing_fields'].append('unknown source')
            return results

    def _validate_snapshot_data(self, snapshot, results):
        """Validate snapshot data with Greeks"""
        if not snapshot:
            results['missing_fields'].append('snapshot is None')
            return results

        # Check for Greeks object
        greeks = snapshot.get('greeks')
        if not greeks:
            results['missing_fields'].append('greeks object')
            print(f"   ❌ No 'greeks' object in snapshot")
            return results

        # Required Greeks fields
        required_greeks = {
            'delta': 'Delta (Δ) - Price sensitivity',
            'gamma': 'Gamma (Γ) - Delta sensitivity',
            'theta': 'Theta (Θ) - Time decay',
            'vega': 'Vega - IV sensitivity',
        }

        # Check each Greek
        for greek_name, description in required_greeks.items():
            value = greeks.get(greek_name)
            if value is not None:
                results['greeks'][greek_name] = value
                print(f"   ✅ {description}: {value}")
            else:
                results['missing_fields'].append(greek_name)
                print(f"   ❌ Missing: {description}")

        # Check for implied volatility
        iv = snapshot.get('implied_volatility')
        if iv is not None:
            results['greeks']['iv'] = iv
            print(f"   ✅ Implied Volatility (IV): {iv}")
        else:
            results['missing_fields'].append('implied_volatility')
            print(f"   ❌ Missing: Implied Volatility")

        # Extract other useful details
        details_fields = {
            'last_quote': ['bid', 'ask', 'bid_size', 'ask_size'],
            'day': ['open', 'high', 'low', 'close', 'volume'],
        }

        for section, fields in details_fields.items():
            section_data = snapshot.get(section, {})
            for field in fields:
                value = section_data.get(field)
                if value is not None:
                    results['details'][field] = value

        # Validation result
        results['valid'] = len(results['missing_fields']) == 0
        return results

    def _validate_contract_data(self, contract, results):
        """Validate contract details data (no Greeks)"""
        if not contract:
            results['missing_fields'].append('contract is None')
            return results

        print(f"   ℹ️  Contract endpoint does not provide Greeks")
        print(f"   ℹ️  Showing available contract details instead:\n")

        # Extract contract details
        contract_fields = {
            'contract_type': 'Type',
            'exercise_style': 'Exercise Style',
            'expiration_date': 'Expiration',
            'strike_price': 'Strike Price',
            'underlying_ticker': 'Underlying',
            'shares_per_contract': 'Shares/Contract',
            'ticker': 'Option Ticker'
        }

        for field, label in contract_fields.items():
            value = contract.get(field)
            if value is not None:
                results['contract_details'][field] = value
                print(f"   ✅ {label}: {value}")

        # Mark as having limited data
        results['missing_fields'].append('greeks (requires OPTIONS subscription)')
        results['valid'] = False  # Not valid for Greeks POC, but connection works

        return results


def test_polygon_greeks(api_key, underlying="SPY"):
    """
    Test Polygon.io options data fetching

    Args:
        api_key: Polygon.io API key
        underlying: Underlying symbol to test (default: SPY)

    Returns:
        Validation results dictionary
    """
    print("=" * 80)
    print("POC #2: Polygon.io Options Data Fetching")
    print("=" * 80)

    # Create validator
    validator = PolygonGreeksValidator(api_key)

    # Get an option contract ticker
    option_ticker = validator.get_option_contract(underlying)

    # Fetch data (snapshot or contract details)
    response = validator.get_option_snapshot(option_ticker)

    # Validate data
    validation = validator.validate_greeks(response)

    # Print results
    print("\n" + "=" * 80)
    print("POC #2 RESULTS")
    print("=" * 80)

    source = validation.get('source', 'unknown')

    if validation['valid']:
        print("\n✅ POC #2 PASSED - All required Greeks are available!")
        print(f"   Data source: {source} endpoint")
        print("\n📊 Greeks Found:")
        for greek, value in validation['greeks'].items():
            print(f"   {greek}: {value}")

        if validation['details']:
            print("\n📈 Additional Details:")
            for field, value in validation['details'].items():
                print(f"   {field}: {value}")

        print("\n🎯 Next Steps:")
        print("   1. ✅ Polygon.io connection works")
        print("   2. ✅ All Greeks data available")
        print("   3. ⏭️  Move to POC #3 (Grouping Algorithm)")

    elif source == 'contract':
        print("\n⚠️  POC #2 PARTIAL - Connection works, but Greeks unavailable")
        print(f"   Data source: {source} endpoint")

        if validation['contract_details']:
            print("\n📋 Contract Details Retrieved:")
            for field, value in validation['contract_details'].items():
                print(f"   {field}: {value}")

        print("\n🔒 Subscription Limitation:")
        print("   Your Polygon.io subscription does not include OPTIONS tier")
        print("   Greeks data (delta, gamma, theta, vega, IV) requires upgrade")

        print("\n💡 Options:")
        print("   1. Upgrade to Polygon.io OPTIONS subscription (~$99/month)")
        print("      https://polygon.io/pricing")
        print("   2. Use IBKR API for Greeks (you already have IBKR connection)")
        print("   3. Continue without Greeks for now")

        print("\n🎯 Next Steps:")
        print("   1. ✅ Polygon.io connection works")
        print("   2. ✅ Can fetch option contract details")
        print("   3. ❌ Greeks require subscription upgrade OR alternative source")
        print("   4. ⏭️  Consider POC #3 (Grouping Algorithm) to continue progress")

    else:
        print("\n❌ POC #2 FAILED - Could not fetch option data!")
        print("\n⚠️  Missing Fields:")
        for field in validation['missing_fields']:
            print(f"   - {field}")

        print("\n🔍 Troubleshooting:")
        print("   1. Verify the option contract exists")
        print("   2. Check expiration date hasn't passed")
        print("   3. Try a different underlying or contract")

        if validation['greeks']:
            print("\n📊 Available Greeks:")
            for greek, value in validation['greeks'].items():
                print(f"   {greek}: {value}")

    print("=" * 80)

    return validation


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    # Get API key from environment
    api_key = os.getenv("POLYGON_API_KEY")

    if not api_key:
        print("❌ ERROR: POLYGON_API_KEY not found in environment")
        print("\nPlease:")
        print("1. Copy .env.example to .env")
        print("2. Add your Polygon.io API key to .env")
        print("3. Run this script again")
        exit(1)

    # Test with SPY (most liquid, always has data)
    underlying = os.getenv("TEST_UNDERLYING", "SPY")

    # Run the test
    validation = test_polygon_greeks(api_key, underlying)

    # Exit with appropriate code
    source = validation.get('source')

    if validation['valid']:
        print("\n✅ SUCCESS: Polygon.io provides all required Greeks data")
        exit(0)
    elif source == 'contract':
        print("\n⚠️  PARTIAL SUCCESS: Polygon.io connection works")
        print("   Greeks data requires OPTIONS subscription upgrade")
        print("   Consider using IBKR API for Greeks instead")
        exit(0)  # Exit successfully - connection works, just limited by subscription
    else:
        print("\n❌ FAILURE: Could not fetch option data from Polygon.io")
        exit(1)

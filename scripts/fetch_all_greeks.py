#!/usr/bin/env python3
"""Fetch Greeks for all closed trades that don't have them."""

import asyncio
import httpx
import sys

API_BASE = "http://localhost:8000/api/v1"


async def fetch_greeks_for_trade(client: httpx.AsyncClient, trade_id: int) -> tuple[int, bool, str]:
    """Fetch Greeks for a single trade."""
    try:
        response = await client.post(
            f"{API_BASE}/trade-analytics/{trade_id}/fetch-greeks",
            json={},
            timeout=30.0,
        )
        if response.status_code == 200:
            data = response.json()
            return trade_id, data.get("success", False), data.get("message", "")
        else:
            return trade_id, False, f"HTTP {response.status_code}"
    except Exception as e:
        return trade_id, False, str(e)


async def main():
    async with httpx.AsyncClient() as client:
        # Get all closed trades
        response = await client.get(f"{API_BASE}/trades?status=CLOSED&limit=500")
        if response.status_code != 200:
            print(f"Failed to fetch trades: {response.status_code}")
            sys.exit(1)

        trades = response.json().get("trades", [])

        # Filter to trades without Greeks
        trades_to_fetch = [t for t in trades if t.get("delta_open") is None]

        print(f"Found {len(trades_to_fetch)} closed trades without Greeks")

        if not trades_to_fetch:
            print("All trades already have Greeks!")
            return

        succeeded = 0
        failed = 0

        # Process in batches of 5 to avoid overwhelming the API
        batch_size = 5
        for i in range(0, len(trades_to_fetch), batch_size):
            batch = trades_to_fetch[i:i + batch_size]

            # Fetch concurrently within batch
            tasks = [fetch_greeks_for_trade(client, t["id"]) for t in batch]
            results = await asyncio.gather(*tasks)

            for trade_id, success, message in results:
                if success:
                    succeeded += 1
                    print(f"  [{succeeded + failed}/{len(trades_to_fetch)}] Trade {trade_id}: OK")
                else:
                    failed += 1
                    print(f"  [{succeeded + failed}/{len(trades_to_fetch)}] Trade {trade_id}: FAILED - {message}")

            # Small delay between batches to be nice to the API
            if i + batch_size < len(trades_to_fetch):
                await asyncio.sleep(0.5)

        print(f"\nComplete! Succeeded: {succeeded}, Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(main())

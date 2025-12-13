#!/usr/bin/env python3
"""Test IBKR connection directly."""

import asyncio
from ib_insync import IB

async def test_connection():
    ib = IB()
    try:
        print("Attempting to connect to IBKR...")
        print(f"Host: 127.0.0.1")
        print(f"Port: 7496")
        print(f"Client ID: 0")

        await ib.connectAsync('127.0.0.1', 7496, clientId=0, timeout=10)

        print("✅ Connected successfully!")
        print(f"Connection status: {ib.isConnected()}")

        # Try to get positions
        positions = ib.positions()
        print(f"\nFound {len(positions)} positions:")
        for pos in positions:
            print(f"  - {pos.contract.symbol}: {pos.position} @ {pos.avgCost}")

        ib.disconnect()

    except Exception as e:
        print(f"❌ Connection failed!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print(f"Error repr: {repr(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())

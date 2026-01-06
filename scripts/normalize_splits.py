"""Normalize executions affected by stock splits."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from trading_journal.config import get_settings
from trading_journal.services.split_normalization_service import SplitNormalizationService

settings = get_settings()


async def normalize_splits():
    """Run split normalization on all affected executions."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        service = SplitNormalizationService(session)

        # First check what needs normalization
        print("Checking for unnormalized splits...")
        report = await service.check_for_unnormalized_splits()

        if report["total_suspicious"] > 0:
            print(f"\nFound {report['total_suspicious']} executions that may need normalization:")
            for issue in report["potential_issues"]:
                print(f"  {issue['symbol']}: {issue['options_count']} options, {issue['stocks_count']} stocks")
                print(f"    Split: {issue['split_ratio']}:1 on {issue['split_date']}")
                if issue["sample_strikes"]:
                    print(f"    Sample strikes: {issue['sample_strikes']}")
        else:
            print("No unnormalized executions found.")

        # Run normalization
        print("\nNormalizing all splits...")
        stats = await service.normalize_all_splits()

        print(f"\nNormalization complete:")
        print(f"  Symbols checked: {stats['symbols_checked']}")
        print(f"  Total normalized: {stats['executions_normalized']}")
        print(f"  Options: {stats['options_normalized']}")
        print(f"  Stocks: {stats['stocks_normalized']}")

        if stats["by_symbol"]:
            print("\nBy symbol:")
            for symbol, result in stats["by_symbol"].items():
                print(f"  {symbol}: {result['total']} ({result['options']} options, {result['stocks']} stocks)")

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(normalize_splits())

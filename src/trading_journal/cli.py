"""Command-line interface using Typer."""

import typer
from rich.console import Console

from trading_journal import __version__

app = typer.Typer(
    name="trading-journal",
    help="Trading Journal - Options trading tracker and analyzer",
    add_completion=False,
)
console = Console()


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        console.print(f"Trading Journal version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
):
    """Trading Journal CLI."""
    pass


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start the FastAPI server."""
    import uvicorn

    console.print(f"[green]Starting Trading Journal API on {host}:{port}[/green]")
    uvicorn.run(
        "trading_journal.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def sync(
    days: int = typer.Option(7, "--days", help="Days to look back"),
):
    """Sync executions from IBKR."""
    import asyncio

    import httpx

    async def do_sync():
        async with httpx.AsyncClient() as client:
            console.print(f"[yellow]Syncing executions from IBKR (last {days} days)...[/yellow]")
            try:
                response = await client.post(
                    "http://localhost:8000/api/v1/executions/sync",
                    json={"days_back": days},
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                console.print(f"[green]✓ {data['message']}[/green]")
                console.print(f"  Fetched: {data['fetched']}")
                console.print(f"  New: {data['new']}")
                console.print(f"  Existing: {data['existing']}")
                if data['errors'] > 0:
                    console.print(f"  [red]Errors: {data['errors']}[/red]")
            except httpx.HTTPError as e:
                console.print(f"[red]✗ Sync failed: {e}[/red]")
                console.print("[yellow]Make sure the API server is running (trading-journal serve)[/yellow]")

    asyncio.run(do_sync())


@app.command()
def process(
    underlying: str = typer.Option(None, "--underlying", help="Filter by underlying"),
):
    """Process executions into trades."""
    import asyncio

    import httpx

    async def do_process():
        async with httpx.AsyncClient() as client:
            console.print("[yellow]Processing executions into trades...[/yellow]")
            try:
                payload = {}
                if underlying:
                    payload["underlying"] = underlying

                response = await client.post(
                    "http://localhost:8000/api/v1/trades/process",
                    json=payload,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                console.print(f"[green]✓ {data['message']}[/green]")
                console.print(f"  Executions: {data['executions_processed']}")
                console.print(f"  Trades: {data['trades_created']}")
            except httpx.HTTPError as e:
                console.print(f"[red]✗ Processing failed: {e}[/red]")
                console.print("[yellow]Make sure the API server is running (trading-journal serve)[/yellow]")

    asyncio.run(do_process())


@app.command()
def fetch_greeks():
    """Fetch Greeks for open positions."""
    console.print("[yellow]Fetching Greeks for open positions...[/yellow]")
    console.print("[red]Not implemented yet - coming in Phase 2[/red]")


@app.command()
def status():
    """Show trading journal status."""
    from trading_journal import __version__

    console.print(f"[bold]Trading Journal v{__version__}[/bold]")
    console.print("[green]Status: Ready[/green]")


if __name__ == "__main__":
    app()

"""Command Line Interface (CLI) runner powered by Typer and Rich."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from clients.erp_client import MockERPClient
from core.exceptions import OrderNotFoundError

app = typer.Typer(
    help="Customer Support Automation Agent CLI runner and diagnostics tool."
)
console = Console()


@app.command()
def info() -> None:
    """Display project and environment information."""
    console.print(
        Panel(
            "[bold cyan]8_support_agent[/bold cyan]\n"
            "Autonomous Tier-1 Customer Support Automation Agent\n"
            "Stack: FastAPI | Pydantic V2 | ReAct FSM | MCP Runtime",
            title="Service Diagnostics",
        )
    )


@app.command()
def check_order(
    order_id: str = typer.Argument(..., help="Order ID (CMD-XXXXX)"),
) -> None:
    """Inspect order record in mock ERP database."""
    client = MockERPClient()
    try:
        order = client.get_order_by_id(order_id)
        table = Table(title=f"Order Details: {order_id}")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Customer Email", str(order.get("customer_email")))
        table.add_row("Status", str(order.get("status")))
        table.add_row("Carrier", str(order.get("carrier")))
        table.add_row("Tracking", str(order.get("tracking_number")))
        table.add_row(
            "Items Total (€)", f"{order.get('items_total_ttc_cents', 0) / 100:.2f}"
        )
        table.add_row("Express Shipping", str(order.get("is_express")))

        console.print(table)
    except OrderNotFoundError:
        console.print(f"[bold red]Order '{order_id}' not found in mock ERP.[/bold red]")


@app.command()
def run(
    email_file: Path = typer.Option(None, "--file", "-f", help="Path to email file"),
) -> None:
    """Execute support agent on input email."""
    if email_file and email_file.exists():
        console.print(f"[green]Processing email file: {email_file}[/green]")
    else:
        console.print("[yellow]Agent runner ready for Phase 8 qualification.[/yellow]")


if __name__ == "__main__":
    app()

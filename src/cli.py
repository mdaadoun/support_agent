"""Command Line Interface (CLI) runner powered by Typer and Rich."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import typer
from cli_display import (
    render_diagnostics,
    render_order_details,
    render_output,
)
from rich.console import Console
from rich.panel import Panel

from api.service import AgentService
from clients.erp_client import MockERPClient
from core.exceptions import OrderNotFoundError, SupportAgentBaseError
from models.email import InboundEmailMessage
from models.response import AgentFinalResponse
from models.session import AgentSessionSnapshot

app = typer.Typer(
    help="Customer Support Automation Agent CLI runner and diagnostics tool."
)
console = Console()

__all__ = ["app", "check_order", "execute_agent", "info", "interactive", "run"]


@app.command()
def info() -> None:
    """Display project and environment information."""
    render_diagnostics(console)


@app.command()
def check_order(
    order_id: str = typer.Argument(..., help="Order ID (CMD-XXXXX)"),
) -> None:
    """Inspect order record in mock ERP database."""
    client = MockERPClient()
    try:
        order = client.get_order_by_id(order_id)
        render_order_details(console, order, order_id)
    except OrderNotFoundError:
        console.print(f"[bold red]Order '{order_id}' not found in mock ERP.[/bold red]")


def _parse_email_file(file_path: Path) -> InboundEmailMessage:
    """Load and validate InboundEmailMessage from JSON or structured text file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    raw = file_path.read_text(encoding="utf-8").strip()
    if raw.startswith("{"):
        try:
            return InboundEmailMessage.model_validate_json(raw)
        except Exception:
            pass

    subject, sender, body_lines = "Customer Inquiry", "customer@example.com", []
    for line in raw.splitlines():
        lower = line.lower()
        if lower.startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
        elif lower.startswith("from:"):
            sender = line.split(":", 1)[1].strip()
        else:
            body_lines.append(line)

    return InboundEmailMessage(
        message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
        sender_email=sender,
        subject=subject,
        body_text="\n".join(body_lines).strip() or raw,
        received_at=datetime.now(timezone.utc),
    )


def execute_agent(
    message: InboundEmailMessage,
    tenant_id: str = "default_tenant",
    service: AgentService | None = None,
) -> tuple[AgentFinalResponse, AgentSessionSnapshot]:
    """Execute support agent synchronously via AgentService."""
    svc = service or AgentService()
    response = asyncio.run(svc.process_email(message, tenant_id=tenant_id))
    snapshot = asyncio.run(svc.get_session(response.session_id, tenant_id=tenant_id))
    return response, snapshot


def _process_run(
    email_file: Path | None = None,
    sender: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    interactive_mode: bool = False,
    tenant_id: str = "default_tenant",
    json_output: bool = False,
) -> None:
    """Core execution logic shared between run and interactive commands."""
    try:
        if interactive_mode:
            sender = typer.prompt("Sender Email", default="customer@example.com")
            subject = typer.prompt("Subject", default="Order Status Inquiry")
            body = typer.prompt("Message Body")

        if email_file is not None:
            message = _parse_email_file(email_file)
        elif sender and body:
            message = InboundEmailMessage(
                message_id=f"MSG-{uuid.uuid4().hex[:8].upper()}",
                sender_email=sender,
                subject=subject or "Customer Inquiry",
                body_text=body,
                received_at=datetime.now(timezone.utc),
            )
        else:
            console.print(
                "[bold red]Error: Provide --file, --interactive, or --sender and --body.[/bold red]"
            )
            raise typer.Exit(code=1)

        with console.status(
            "[bold green]Executing agent reasoning loop...[/bold green]"
        ):
            response, snapshot = execute_agent(message, tenant_id=tenant_id)

        if json_output:
            console.print_json(response.model_dump_json(indent=2))
        else:
            render_output(console, response, snapshot)

    except SupportAgentBaseError as exc:
        console.print(
            Panel(
                f"[bold red]{exc.error_code}:[/bold red] {exc.message}",
                title="Agent Error",
            )
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[bold red]Error: {exc}[/bold red]")
        raise typer.Exit(code=1) from exc


@app.command()
def run(
    email_file: Path | None = typer.Option(
        None, "--file", "-f", help="Path to email file"
    ),
    sender: str | None = typer.Option(None, "--sender", "-s", help="Sender email"),
    subject: str | None = typer.Option(None, "--subject", "-sub", help="Subject line"),
    body: str | None = typer.Option(None, "--body", "-b", help="Body text"),
    interactive_mode: bool = typer.Option(
        False, "--interactive", "-i", help="Interactive prompt"
    ),
    tenant_id: str = typer.Option("default_tenant", "--tenant", "-t", help="Tenant ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Print JSON output"),
) -> None:
    """Execute autonomous support agent on input email or interactive prompt."""
    _process_run(
        email_file=email_file,
        sender=sender,
        subject=subject,
        body=body,
        interactive_mode=interactive_mode,
        tenant_id=tenant_id,
        json_output=json_output,
    )


@app.command(name="interactive")
def interactive(
    tenant_id: str = typer.Option("default_tenant", "--tenant", "-t", help="Tenant ID"),
) -> None:
    """Start interactive query session for customer support."""
    _process_run(interactive_mode=True, tenant_id=tenant_id)


if __name__ == "__main__":
    app()

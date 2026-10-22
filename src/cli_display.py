"""Rich console presentation components and formatted tables for CLI runner."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from models.response import AgentFinalResponse
from models.session import AgentSessionSnapshot

__all__ = [
    "render_diagnostics",
    "render_order_details",
    "render_output",
    "render_traces",
]


def render_diagnostics(console: Console) -> None:
    """Display project and environment information panel."""
    console.print(
        Panel(
            "[bold cyan]8_support_agent[/bold cyan]\n"
            "Autonomous Tier-1 Customer Support Automation Agent\n"
            "Stack: FastAPI | Pydantic V2 | ReAct FSM | MCP Runtime",
            title="Service Diagnostics",
        )
    )


def render_order_details(
    console: Console, order: dict[str, Any], order_id: str
) -> None:
    """Render ERP order details table."""
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


def render_traces(console: Console, snapshot: AgentSessionSnapshot) -> None:
    """Render tool execution traces in a formatted Rich table."""
    table = Table(
        title=f"ReAct Tool Execution Traces ({len(snapshot.tool_traces)} tool calls)",
        expand=True,
    )
    table.add_column("#", style="cyan", width=4)
    table.add_column("Tool", style="magenta", width=26)
    table.add_column("Arguments", style="dim")
    table.add_column("Status", width=10)
    table.add_column("Duration", justify="right", width=12)

    for idx, trace in enumerate(snapshot.tool_traces, 1):
        status_str = (
            "[bold green]SUCCESS[/bold green]"
            if trace.result.success
            else "[bold red]FAILED[/bold red]"
        )
        args_str = json.dumps(trace.arguments, default=str)
        table.add_row(
            str(idx),
            trace.tool_name,
            args_str,
            status_str,
            f"{trace.duration_ms:.1f}ms",
        )
    console.print(table)


def render_output(
    console: Console, response: AgentFinalResponse, snapshot: AgentSessionSnapshot
) -> None:
    """Render executive summary, trace table, and certified response panels."""
    color = (
        "green"
        if response.status_resolution.value == "RESOLVED_AUTOMATICALLY"
        else "yellow"
    )
    summary_text = (
        f"[bold]Session ID:[/bold] {response.session_id}  |  "
        f"[bold]Intent:[/bold] {response.intent.value}  |  "
        f"[bold]Confidence:[/bold] {response.confidence_score:.2f}  |  "
        f"[bold]Status:[/bold] [{color}]{response.status_resolution.value}[/{color}]\n"
        f"[bold]Order ID:[/bold] {response.order_id or 'None'}  |  "
        f"[bold]Technical Summary:[/bold] {response.internal_technical_summary}"
    )
    if response.human_escalation_reason:
        summary_text += f"\n[bold red]Escalation Reason:[/bold red] {response.human_escalation_reason}"
    console.print(Panel(summary_text, title="Execution Summary", border_style=color))

    if snapshot.tool_traces:
        render_traces(console, snapshot)

    resp_content = (
        f"[bold cyan]Subject:[/bold cyan] {response.email_response_subject}\n\n"
        f"{response.email_response_body}"
    )
    console.print(
        Panel(resp_content, title="Certified Email Response", border_style="blue")
    )

    telemetry = (
        f"[dim]Tokens: {response.tokens_prompt} prompt / {response.tokens_completion} completion  |  "
        f"Cost: ${response.cost_estimation_usd:.5f}  |  "
        f"Execution Time: {response.execution_time_seconds:.2f}s[/dim]"
    )
    console.print(telemetry)

"""
omium-txn-demo — Stablecoin Transaction Processing Agent
=========================================================
A LangGraph pipeline with 5 steps, full OpenTelemetry tracing,
and Omium SDK integration for execution tracking and checkpoints.

Usage:
    python main.py              # interactive CLI loop
    python main.py --demo       # run all 5 demo scenarios automatically
    omium run main.py           # run via Omium CLI (traces appear in dashboard)
"""

import operator
import os
import sys
import time
from typing import Annotated, Any, Dict, List, Optional

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from typing_extensions import TypedDict

load_dotenv()

# ── Omium SDK init (optional — project works perfectly without it) ───────────
_omium_enabled = False
_omium_status = "not configured"

_api_key = os.environ.get("OMIUM_API_KEY", "")
if _api_key:
    try:
        import omium as _omium_sdk
        _project = os.environ.get("OMIUM_PROJECT", "").strip() or None
        _omium_sdk.init(
            api_key=_api_key,
            project=_project,
            auto_trace=True,
            auto_checkpoint=True,
            api_base_url=os.environ.get("OMIUM_API_URL", "https://api.omium.ai"),
        )
        _omium_sdk.instrument_langgraph()
        _omium_enabled = True
        _omium_status = "connected"
    except ImportError:
        _omium_status = "sdk not installed (pip install omium)"
    except Exception as _e:
        _omium_status = f"init failed: {_e}"

# ── OTel setup (always on — shows traces in console) ────────────────────────
from telemetry import setup_telemetry

setup_telemetry()

# ── Step imports ─────────────────────────────────────────────────────────────
from steps.audit_logger import audit_log
from steps.executor import execute_transaction
from steps.intent_parser import parse_intent
from steps.risk_scorer import score_risk
from steps.validator import validate

console = Console()


# ── State ────────────────────────────────────────────────────────────────────
class TransactionState(TypedDict):
    message: str
    intent: Optional[Dict]
    validation: Optional[Dict]
    risk: Optional[Dict]
    execution: Optional[Dict]
    audit: Optional[Dict]
    final_status: str
    error_step: Optional[str]
    step_timings: Annotated[List[Dict], operator.add]
    retry_count: int


# ── Routing ───────────────────────────────────────────────────────────────────
def route_after_intent(state: TransactionState) -> str:
    return "audit_logger" if state.get("final_status") in ("FAILED", "BLOCKED") else "validator"


def route_after_validator(state: TransactionState) -> str:
    return "audit_logger" if state.get("final_status") in ("FAILED", "BLOCKED") else "risk_scorer"


def route_after_risk(state: TransactionState) -> str:
    return "audit_logger" if state.get("final_status") in ("FAILED", "BLOCKED") else "executor"


# ── Build graph ───────────────────────────────────────────────────────────────
def build_graph() -> StateGraph:
    g = StateGraph(TransactionState)

    g.add_node("intent_parser", parse_intent)
    g.add_node("validator", validate)
    g.add_node("risk_scorer", score_risk)
    g.add_node("executor", execute_transaction)
    g.add_node("audit_logger", audit_log)

    g.add_edge(START, "intent_parser")
    g.add_conditional_edges("intent_parser", route_after_intent)
    g.add_conditional_edges("validator", route_after_validator)
    g.add_conditional_edges("risk_scorer", route_after_risk)
    g.add_edge("executor", "audit_logger")
    g.add_edge("audit_logger", END)

    return g.compile()


graph = build_graph()


# ── Run pipeline ──────────────────────────────────────────────────────────────
def run_pipeline(message: str) -> TransactionState:
    tracer = trace.get_tracer("transaction.agent")

    with tracer.start_as_current_span("transaction.process") as root_span:
        root_span.set_attribute("input.message", message)

        initial_state: TransactionState = {
            "message": message,
            "intent": None,
            "validation": None,
            "risk": None,
            "execution": None,
            "audit": None,
            "final_status": "PENDING",
            "error_step": None,
            "step_timings": [],
            "retry_count": 0,
        }

        result = graph.invoke(initial_state)
        root_span.set_attribute("output.final_status", result.get("final_status", "UNKNOWN"))

        if result.get("final_status") in ("FAILED", "BLOCKED"):
            root_span.set_status(StatusCode.ERROR, result.get("error_step", "unknown"))

        return result


# ── Display ───────────────────────────────────────────────────────────────────
STATUS_STYLE = {
    "APPROVED": "bold green",
    "BLOCKED": "bold yellow",
    "FAILED": "bold red",
    "PENDING": "bold blue",
}

STATUS_ICON = {
    "APPROVED": "✅  APPROVED",
    "BLOCKED": "🚫  BLOCKED",
    "FAILED": "❌  FAILED",
    "PENDING": "⏳  PENDING",
}


def display_result(result: TransactionState, elapsed_ms: int) -> None:
    final = result.get("final_status", "UNKNOWN")

    table = Table(
        title="Pipeline Step Results",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Step", style="bold white", width=22)
    table.add_column("Status", justify="center", width=6)
    table.add_column("ms", justify="right", width=7)
    table.add_column("Detail", style="dim")

    all_steps = ["IntentParser", "Validator", "RiskScorer", "ExecutionSimulator", "AuditLogger"]
    timings_by_step = {t["step"]: t for t in result.get("step_timings", [])}

    for step in all_steps:
        if step in timings_by_step:
            t = timings_by_step[step]
            icon = t["status"]
            style = "green" if icon == "✓" else "red"
            table.add_row(
                step,
                f"[{style}]{icon}[/{style}]",
                str(t["duration_ms"]),
                t.get("detail", ""),
            )
        else:
            table.add_row(step, "[dim]—[/dim]", "—", "[dim]skipped[/dim]")

    console.print()
    console.print(table)

    style = STATUS_STYLE.get(final, "bold white")
    icon = STATUS_ICON.get(final, final)
    console.print(
        Panel(
            f"[{style}]{icon}[/{style}]  [dim](total {elapsed_ms}ms)[/dim]",
            expand=False,
        )
    )

    if final == "APPROVED" and result.get("execution"):
        ex = result["execution"]
        console.print(
            f"  [green]tx:[/green] {ex.get('tx_hash', '')[:20]}...  "
            f"[green]gas:[/green] {ex.get('gas_estimate')}  "
            f"[green]confirm:[/green] {ex.get('confirmation_time_s')}s"
        )

    if _omium_enabled:
        console.print("  [dim cyan]↗  Trace sent to Omium dashboard[/dim cyan]")


# ── Demo scenarios ────────────────────────────────────────────────────────────
DEMO_SCENARIOS = [
    ("1 — Valid tx",           "Send 500 USDC to 0x742d35Cc6634C0532925a3b8D4C9C4E4F8b3e1a2"),
    ("2 — High risk",          "Transfer 75000 USDT to 0x9A8f7e4d3c2b1a0987654321fedcba0987654321"),
    ("3 — Bad address",        "Pay 100 USDC to 0xINVALID"),
    ("4 — Ambiguous message",  "send some money to my friend"),
    ("5 — Max amount edge",    "Send 100000 USDC to 0x742d35Cc6634C0532925a3b8D4C9C4E4F8b3e1a2"),
]


def run_demo() -> None:
    omium_line = (
        "[dim green]✓ Omium SDK connected[/dim green]"
        if _omium_enabled
        else f"[dim yellow]⚠ Omium: {_omium_status}[/dim yellow]"
    )
    console.print(
        Panel(
            f"[bold cyan]omium-txn-demo[/bold cyan]  [dim]— 5 Demo Scenarios[/dim]\n{omium_line}",
            box=box.DOUBLE,
        )
    )

    for label, msg in DEMO_SCENARIOS:
        console.print(f"\n[bold yellow]━━━ Scenario {label} ━━━[/bold yellow]")
        console.print(f"[bold]Message:[/bold] [italic]{msg}[/italic]")
        t0 = time.time()
        result = run_pipeline(msg)
        elapsed = round((time.time() - t0) * 1000)
        display_result(result, elapsed)
        time.sleep(0.3)

    console.print("\n[dim]Demo complete. Check transactions.log for audit trail.[/dim]")
    if _omium_enabled:
        console.print("[dim cyan]Check your Omium dashboard for execution traces.[/dim cyan]")


# ── Interactive CLI ────────────────────────────────────────────────────────────
def run_cli() -> None:
    omium_line = (
        "[dim green]✓ Omium SDK connected — traces will appear in dashboard[/dim green]"
        if _omium_enabled
        else f"[dim yellow]⚠ Omium: {_omium_status}[/dim yellow]"
    )
    console.print(
        Panel(
            f"[bold cyan]omium-txn-demo[/bold cyan]  [dim]Stablecoin Transaction Agent[/dim]\n{omium_line}",
            box=box.DOUBLE,
        )
    )
    console.print("[dim]Type a transaction message or 'quit' to exit. Try: 'demo' to run all scenarios.[/dim]\n")

    while True:
        try:
            msg = console.input("[bold cyan]>[/bold cyan] Enter transaction message: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not msg:
            continue
        if msg.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if msg.lower() == "demo":
            run_demo()
            continue

        t0 = time.time()
        result = run_pipeline(msg)
        elapsed = round((time.time() - t0) * 1000)
        display_result(result, elapsed)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo()
    else:
        run_cli()

"""PyChronicle Typer Command-Line Interface.

Provides CLI commands for:
- `pychronicle run <target>`: Validate, parse AST, trace execution, store deltas, and launch Textual TUI.
- `pychronicle debug <target>`: Trace execution and print step-by-step terminal timeline summary.
- `pychronicle validate <target>`: Validate file, syntax, AST, and database without executing.
- `pychronicle history`: List recorded execution sessions and status ledgers.
- `pychronicle replay <session_id>`: Reconstruct and inspect historical states at specific steps.
"""

from pathlib import Path
import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from pychronicle.ast_parser import parse_file
from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH
from pychronicle.debugger import Debugger
from pychronicle.exceptions import PyChronicleError
from pychronicle.replay import ReplayEngine
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session
from pychronicle.validation import validate_target_file

app = typer.Typer(
    name="pychronicle",
    help="PyChronicle — AST-Powered Python Time-Travel Debugger & Workspace.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    target: Path = typer.Argument(..., help="Path to Python script to trace and debug in TUI."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database or in-memory."),
    watch: Optional[List[str]] = typer.Option(None, "--watch", "-w", help="Variable name(s) to watch."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose diagnostic output."),
) -> None:
    """Validate, parse AST, trace execution under sys.settrace(), and launch interactive Textual TUI."""
    # 1. Validation
    val_res = validate_target_file(target)
    if not val_res.is_valid:
        console.print(f"[bold red]Validation Failed:[/bold red]\n{val_res.error_message}")
        raise typer.Exit(code=1)

    for warning in val_res.warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")

    # 2. Execution Tracing
    config = ChronicleConfig(db_path=db, verbose=verbose)
    storage = SQLiteStorage(db_path=db)

    try:
        result = run_debug_session(target_path=target, config=config, storage=storage)
    except PyChronicleError as e:
        console.print(f"[bold red]Debugger Error: {e}[/bold red]")
        raise typer.Exit(code=1)

    if result.total_steps == 0:
        console.print("[yellow]Execution completed with 0 steps.[/yellow]")
        if result.error:
            console.print(f"[red]Error: {result.error}[/red]")
        return

    # 3. Launch Textual TUI
    if result.replay:
        from pychronicle.tui import PyChronicleTUI

        tui_app = PyChronicleTUI(
            replay=result.replay,
            source_file=target,
            watch_vars=watch or [],
        )
        tui_app.run()


@app.command()
def debug(
    target: Path = typer.Argument(..., help="Path to Python script to trace."),
    tui: bool = typer.Option(False, "--tui", help="Launch Textual TUI upon completion."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database."),
    watch: Optional[List[str]] = typer.Option(None, "--watch", "-w", help="Variable name(s) to watch."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """Debug a Python target file and display execution history summary."""
    config = ChronicleConfig(db_path=db, verbose=verbose)
    storage = SQLiteStorage(db_path=db)

    try:
        result = run_debug_session(target_path=target, config=config, storage=storage)
    except PyChronicleError as e:
        console.print(f"[bold red]Debugger Error: {e}[/bold red]")
        raise typer.Exit(code=1)

    status_color = "green" if result.status == "SUCCESS" else "red"
    console.print(f"\n[bold]PyChronicle Execution Result[/bold]")
    console.print(f"Target:      {target}")
    console.print(f"Status:      [{status_color}]{result.status}[/{status_color}]")
    console.print(f"Total Steps: {result.total_steps}")
    console.print(f"Session ID:  #{result.session_id}")

    if result.error:
        console.print(f"[yellow]Target Error:\n{result.error}[/yellow]")

    if tui and result.replay:
        from pychronicle.tui import PyChronicleTUI

        tui_app = PyChronicleTUI(replay=result.replay, source_file=target, watch_vars=watch or [])
        tui_app.run()
        return

    if result.replay and result.total_steps > 0:
        table = Table(title=f"Execution History ({result.total_steps} Steps)")
        table.add_column("Step", style="cyan", justify="right")
        table.add_column("Line", style="magenta", justify="right")
        table.add_column("Event", style="green")
        table.add_column("Scope", style="yellow")
        table.add_column("Changes", style="white")

        for item in result.replay.get_timeline():
            st = result.replay.get_state_at_step(item["step"])
            chgs = [f"{k}: {c.get('old')} -> {c.get('new')}" for k, c in st.changes.items()]
            chg_str = ", ".join(chgs) if chgs else "-"
            table.add_row(
                str(item["step"]),
                str(item["line"] or "-"),
                item["event"],
                item["scope"],
                chg_str,
            )
        console.print(table)


@app.command()
def validate(
    target: Path = typer.Argument(..., help="Path to Python script to validate."),
) -> None:
    """Validate target file syntax, AST parsing, and readability without running."""
    res = validate_target_file(target)
    if res.is_valid:
        console.print(f"[bold green][PASS] Validation Passed:[/bold green] '{target}'")
        console.print(f"  Lines of Code: {res.line_count}")
        console.print(f"  AST Nodes:     {res.ast_nodes_count}")
    else:
        console.print(f"[bold red][FAIL] Validation Failed:[/bold red] '{target}'")
        console.print(res.error_message)
        raise typer.Exit(code=1)



@app.command(name="history")
def history(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database."),
) -> None:
    """List all recorded execution sessions and snapshot counts."""
    storage = SQLiteStorage(db_path=db)
    session_list = storage.list_sessions()

    if not session_list:
        console.print("[yellow]No debug sessions recorded yet.[/yellow]")
        return

    table = Table(title="PyChronicle Recorded Sessions")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Filename", style="white")
    table.add_column("Status", style="green")
    table.add_column("Steps", justify="right", style="magenta")
    table.add_column("Started At", style="dim")

    for s in session_list:
        st_color = "green" if s["status"] == "SUCCESS" else "red"
        table.add_row(
            str(s["id"]),
            Path(s["filename"]).name,
            f"[{st_color}]{s['status']}[/{st_color}]",
            str(s["step_count"]),
            s["started_at"],
        )
    console.print(table)


@app.command()
def replay(
    session_id: int = typer.Argument(..., help="Session ID to replay."),
    step: Optional[int] = typer.Option(None, "--step", "-s", help="Step number to reconstruct."),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="Path to SQLite database."),
    watch: Optional[List[str]] = typer.Option(None, "--watch", "-w", help="Variables to watch."),
) -> None:
    """Reconstruct historical execution state at any step without re-running code."""
    storage = SQLiteStorage(db_path=db)
    engine = ReplayEngine(session_id=session_id, storage=storage)

    if engine.total_steps == 0:
        console.print(f"[yellow]Session #{session_id} has no recorded steps.[/yellow]")
        return

    if step is not None:
        st = engine.get_state_at_step(step)
        console.print(f"\n[bold cyan]=== Reconstructed State at Step {st.step}/{engine.total_steps} ===[/bold cyan]")
        console.print(f"Line:  {st.line}")
        console.print(f"Event: {st.event}")
        console.print(f"Scope: {st.active_scope}")

        if watch:
            console.print("\n[bold yellow]Watched Variables:[/bold yellow]")
            w_vals = engine.get_watch_values_at(step, watch)
            for k, v in w_vals.items():
                console.print(f"  [W] {k} = {v}")

        console.print("\n[bold]Variables by Scope:[/bold]")
        for s_name, s_vars in st.scopes.items():
            active_flag = " (ACTIVE)" if s_name == st.active_scope else ""
            console.print(f"  Scope: [magenta]{s_name}{active_flag}[/magenta]")
            for k, v in s_vars.items():
                console.print(f"    {k} = {v}")
    else:
        console.print(f"Session #{session_id} contains {engine.total_steps} recorded steps.")
        for s_num in range(1, engine.total_steps + 1):
            st = engine.get_state_at_step(s_num)
            chg_str = ", ".join(f"{k}: {c.get('old')} -> {c.get('new')}" for k, c in st.changes.items())
            console.print(f"Step {s_num:03d} | Line {str(st.line or '-'):>3} | {st.event:<6} | Scope: {st.active_scope:<12} | {chg_str}")



def main_cli() -> None:
    """CLI entry point for pychronicle command."""
    app()


if __name__ == "__main__":
    app()

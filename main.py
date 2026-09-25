"""PyChronicle CLI Entry Point.

Command-line interface for debugging Python scripts, inspecting execution history,
replaying past program states, and launching the interactive TUI.
"""

from pathlib import Path
import sys
from typing import Optional

import click

from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH
from pychronicle.exceptions import PyChronicleError
from pychronicle.replay import ReplayEngine
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.1.0", prog_name="PyChronicle")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
@click.option("--web", is_flag=True, help="Launch interactive Web Developer UI instead of terminal workspace.")
def cli(ctx: click.Context, db_path: Path, web: bool) -> None:
    """PyChronicle — AST-Powered Python Time-Travel Debugger & Programming Workspace."""
    if ctx.invoked_subcommand is None:
        if web:
            from web import create_app
            app = create_app(db_path=db_path)
            click.echo(f"Starting PyChronicle Web Interface at http://127.0.0.1:5000 (Database: {db_path})")
            app.run(host="127.0.0.1", port=5000, debug=False)
        else:
            from pychronicle.app import launch_application
            launch_application(db_path=db_path)


@cli.command()
@click.argument("target", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--tui", is_flag=True, help="Launch interactive Textual TUI dashboard upon execution.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
@click.option("--watch", "-w", "watch_vars", multiple=True, help="Variable name(s) to watch.")
@click.option("--verbose", is_flag=True, help="Display verbose diagnostic outputs.")
def debug(target: Path, tui: bool, db_path: Path, watch_vars: tuple[str, ...], verbose: bool) -> None:
    """Debug a Python target file and capture its execution timeline via tracer backend."""
    click.echo("=" * 60)
    click.echo("PyChronicle")
    click.echo("AST-Powered Time-Travel Debugger")
    click.echo("=" * 60)
    click.echo(f"Target:  {target}")
    click.echo(f"Backend: tracer.py")
    click.echo(f"Storage: {db_path}\n")

    config = ChronicleConfig(db_path=db_path, verbose=verbose)
    storage = SQLiteStorage(db_path=db_path)

    try:
        result = run_debug_session(target_path=target, config=config, storage=storage)
    except PyChronicleError as e:
        click.secho(f"\nDebugger Error: {e}", fg="red", bold=True)
        sys.exit(1)

    click.echo(f"Session ID:   {result.session_id}")
    status_color = "green" if result.status == "SUCCESS" else "red"
    click.echo(f"Status:       ", nl=False)
    click.secho(result.status, fg=status_color, bold=True)
    click.echo(f"Total Steps:  {result.total_steps}")
    click.echo(f"Started At:   {result.started_at}")
    click.echo(f"Finished At:  {result.finished_at}")

    if result.error:
        click.echo("-" * 60)
        click.secho(f"Target Program Error:\n{result.error}", fg="yellow")

    if tui and result.replay:
        from pychronicle.tui import PyChronicleTUI
        app = PyChronicleTUI(replay=result.replay, source_file=target, watch_vars=list(watch_vars))
        app.run()
        return

    # Print execution history summary
    if result.replay and result.total_steps > 0:
        click.echo("\nExecution History")
        click.echo("-" * 60)
        click.echo(f"{'Step':<6} {'Line':<6} {'Event':<10} {'Scope':<16} Changes")
        click.echo("-" * 60)

        timeline = result.replay.get_timeline()
        for item in timeline:
            step_num = item["step"]
            state = result.replay.state_at(step_num)
            
            changes_summary = []
            for k, chg in state.changes.items():
                changes_summary.append(f"{k}: {chg.get('old')} -> {chg.get('new')}")
            
            changes_str = ", ".join(changes_summary) if changes_summary else "-"
            if state.return_value:
                changes_str += f" [ret: {state.return_value}]"
            if state.exception_info:
                changes_str += f" [exc: {state.exception_info}]"

            click.echo(
                f"{item['step']:<6} {str(item['line'] or '-'):<6} {item['event']:<10} {item['scope']:<16} {changes_str}"
            )
        click.echo("-" * 60)

        if watch_vars:
            click.echo("\nWatched Variables History")
            click.echo("-" * 60)
            click.echo(f"{'Step':<6} {'Line':<6} {'Scope':<16} Variable = Value (Change)")
            click.echo("-" * 60)
            for step_num in range(1, result.total_steps + 1):
                state = result.replay.state_at(step_num)
                for var in watch_vars:
                    chg = state.changes.get(var)
                    val = result.replay.get_watch_values_at(step_num, [var]).get(var, "<undefined>")
                    chg_str = f" [{chg.get('operation')}]" if chg else ""
                    click.echo(f"{step_num:<6} {str(state.line or '-'):<6} {state.active_scope:<16} {var} = {val}{chg_str}")
            click.echo("-" * 60)


@cli.command()
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def sessions(db_path: Path) -> None:
    """List all recorded debug sessions."""
    if not db_path.exists():
        click.echo(f"No database found at {db_path}")
        return

    storage = SQLiteStorage(db_path=db_path)
    session_list = storage.list_sessions()

    if not session_list:
        click.echo("No sessions recorded yet.")
        return

    click.echo(f"{'ID':<6} {'Filename':<35} {'Status':<12} {'Steps':<8} {'Started At'}")
    click.echo("-" * 80)
    for s in session_list:
        status_color = "green" if s["status"] == "SUCCESS" else "red"
        short_file = Path(s["filename"]).name
        click.echo(
            f"{s['id']:<6} {short_file:<35} ", nl=False
        )
        click.secho(f"{s['status']:<12} ", fg=status_color, nl=False)
        click.echo(f"{s['step_count']:<8} {s['started_at']}")


@cli.command()
@click.argument("session_id", type=int)
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def inspect(session_id: int, db_path: Path) -> None:
    """Inspect summary and snapshots of a recorded session."""
    storage = SQLiteStorage(db_path=db_path)
    session = storage.get_session(session_id)
    if not session:
        click.secho(f"Session {session_id} not found.", fg="red")
        return

    click.echo(f"Session #{session['id']} — {session['filename']}")
    click.echo(f"Status:      {session['status']}")
    click.echo(f"Started:     {session['started_at']}")
    click.echo(f"Finished:    {session['finished_at']}")
    if session["error"]:
        click.secho(f"Error:       {session['error']}", fg="yellow")

    replay = ReplayEngine(session_id=session_id, storage=storage)
    timeline = replay.get_timeline()
    click.echo(f"\nSnapshots ({len(timeline)} steps):")
    click.echo(f"{'Step':<6} {'Line':<6} {'Event':<10} {'Scope':<16} Changes")
    click.echo("-" * 60)
    for item in timeline:
        state = replay.state_at(item["step"])
        chg_list = [f"{k}: {c.get('old')} -> {c.get('new')}" for k, c in state.changes.items()]
        chg_str = ", ".join(chg_list) if chg_list else "-"
        click.echo(f"{item['step']:<6} {str(item['line'] or '-'):<6} {item['event']:<10} {item['scope']:<16} {chg_str}")


@cli.command()
@click.argument("session_id", type=int)
@click.option("--step", "step_num", type=int, default=None, help="Specific step to reconstruct.")
@click.option("--watch", "-w", "watch_vars", multiple=True, help="Variable name(s) to watch.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def replay(session_id: int, step_num: Optional[int], watch_vars: tuple[str, ...], db_path: Path) -> None:
    """Reconstruct historical program state at a step or walk through time."""
    storage = SQLiteStorage(db_path=db_path)
    replay = ReplayEngine(session_id=session_id, storage=storage)

    if replay.total_steps == 0:
        click.echo("Session contains no recorded steps.")
        return

    if step_num is not None:
        state = replay.state_at(step_num)
        click.echo(f"=== Reconstructed State at Step {state.step}/{replay.total_steps} ===")
        click.echo(f"Line:         {state.line}")
        click.echo(f"Event:        {state.event}")
        click.echo(f"Active Scope: {state.active_scope}")
        if state.return_value:
            click.echo(f"Return Value: {state.return_value}")
        if state.exception_info:
            click.secho(f"Exception:    {state.exception_info}", fg="red")
        
        if watch_vars:
            click.echo("\nWatched Variables:")
            watch_vals = replay.get_watch_values_at(step_num, list(watch_vars))
            for var in watch_vars:
                val = watch_vals.get(var, "<undefined>")
                click.echo(f"  [WATCH] {var} = {val}")

        click.echo("\nVariables by Scope:")
        for s_name, s_vars in state.scopes.items():
            active_marker = " (active)" if s_name == state.active_scope else ""
            click.echo(f"  Scope '{s_name}'{active_marker}:")
            for k, v in s_vars.items():
                click.echo(f"    {k} = {v}")
    else:
        click.echo(f"=== Stepping through Session #{session_id} ({replay.total_steps} Steps) ===")
        for s_idx in range(1, replay.total_steps + 1):
            st = replay.state_at(s_idx)
            click.echo(f"\n[Step {st.step:03d} | Line {st.line:03d} | {st.event:<8} | Scope: {st.active_scope}]")
            if st.changes:
                for var, chg in st.changes.items():
                    click.echo(f"   {chg.get('operation')}: {var} ({chg.get('old')} -> {chg.get('new')})")
            if watch_vars:
                w_vals = replay.get_watch_values_at(s_idx, list(watch_vars))
                w_str = ", ".join(f"{k}={v}" for k, v in w_vals.items() if v is not None)
                if w_str:
                    click.echo(f"   Watched: {w_str}")
            if st.active_variables:
                click.echo(f"   Active Scope Variables: {st.active_variables}")


@cli.command()
@click.argument("session_id", type=int)
@click.option("--watch", "-w", "watch_vars", multiple=True, help="Variable name(s) to watch.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def tui(session_id: int, watch_vars: tuple[str, ...], db_path: Path) -> None:
    """Open interactive Textual TUI for a recorded session."""
    storage = SQLiteStorage(db_path=db_path)
    replay = ReplayEngine(session_id=session_id, storage=storage)
    from pychronicle.tui import PyChronicleTUI
    app = PyChronicleTUI(replay=replay, watch_vars=list(watch_vars))
    app.run()


@cli.command(name="workspace")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def workspace_cmd(db_path: Path) -> None:
    """Launch the interactive PyChronicle Programming Workspace TUI."""
    from pychronicle.app import launch_application
    launch_application(db_path=db_path)


@cli.command(name="ui")
@click.option("--port", "-p", type=int, default=5000, help="Port to host PyChronicle web interface.")
@click.option("--host", "-h", type=str, default="127.0.0.1", help="Host address to bind.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
@click.option("--no-browser", is_flag=True, help="Do not automatically open default browser.")
def launch_ui(port: int, host: str, db_path: Path, no_browser: bool) -> None:
    """Launch the interactive PyChronicle Time-Travel Debugger Web UI."""
    import webbrowser
    from web import create_app
    app = create_app(db_path=db_path)
    url = f"http://{host}:{port}/"
    click.echo(f"Starting PyChronicle Web Interface at {url} (Database: {db_path})")
    if not no_browser:
        webbrowser.open(url)
    app.run(host=host, port=port, debug=False)


@cli.command(name="programs")
@click.option("--search", "-s", type=str, default=None, help="Search query filter.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def list_programs_cmd(search: Optional[str], db_path: Path) -> None:
    """List all saved programs stored in SQLite."""
    from pychronicle.application import ApplicationService
    service = ApplicationService(db_path=db_path)
    progs = service.list_programs(search_query=search)

    if not progs:
        click.echo("No programs stored in database.")
        return

    click.echo(f"{'ID':<6} {'Name':<32} {'Status':<14} {'Runs':<6} {'Last Run'}")
    click.echo("-" * 80)
    for p in progs:
        st = p["last_status"] or "NEVER_RUN"
        st_color = "green" if st == "SUCCESS" else ("red" if "ERROR" in st else "yellow")
        click.echo(f"{p['id']:<6} {p['name']:<32} ", nl=False)
        click.secho(f"{st:<14} ", fg=st_color, nl=False)
        click.echo(f"{p['run_count']:<6} {p['last_run_at'] or 'Never'}")


@cli.command(name="run-program")
@click.argument("program_id", type=int)
@click.option("--watch", "-w", "watch_vars", multiple=True, help="Variable name(s) to watch.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def run_program_cmd(program_id: int, watch_vars: tuple[str, ...], db_path: Path) -> None:
    """Run a saved program through the PyChronicle debugger backend."""
    from pychronicle.application import ApplicationService
    service = ApplicationService(db_path=db_path)
    try:
        res = service.run_program(program_id=program_id, watch_vars=list(watch_vars))
    except Exception as e:
        click.secho(f"Error running program: {e}", fg="red", bold=True)
        sys.exit(1)

    click.echo("=" * 60)
    click.echo(f"Program:    {res['program_name']} (ID #{res['program_id']})")
    status_color = "green" if res["status"] == "SUCCESS" else "red"
    click.echo("Status:     ", nl=False)
    click.secho(res["status"], fg=status_color, bold=True)
    click.echo(f"Steps:      {res['total_steps']}")
    click.echo(f"Duration:   {res['duration_ms']} ms")
    click.echo(f"Session ID: #{res['session_id']}")
    click.echo("=" * 60)

    if res["stdout"]:
        click.echo("Stdout:")
        click.echo(res["stdout"].rstrip())

    if res["error"]:
        click.secho(f"Error:\n{res['error']}", fg="yellow")


@cli.command(name="delete-program")
@click.argument("program_id", type=int)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
def delete_program_cmd(program_id: int, yes: bool, db_path: Path) -> None:
    """Delete a saved program and its execution history."""
    from pychronicle.application import ApplicationService
    service = ApplicationService(db_path=db_path)
    prog = service.get_program(program_id)
    if not prog:
        click.secho(f"Program ID {program_id} not found.", fg="red")
        return

    if not yes:
        if not click.confirm(f"Are you sure you want to delete program '{prog['name']}' and its history?"):
            click.echo("Aborted.")
            return

    service.delete_program(program_id)
    click.secho(f"Program '{prog['name']}' (ID #{program_id}) deleted successfully.", fg="green")


@cli.command(name="run")
@click.argument("target", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
@click.option("--watch", "-w", "watch_vars", multiple=True, help="Variable name(s) to watch.")
@click.option("--verbose", is_flag=True, help="Display verbose diagnostic outputs.")
def run_cmd(target: Path, db_path: Path, watch_vars: tuple[str, ...], verbose: bool) -> None:
    """Validate, parse AST, trace execution under sys.settrace(), and launch Textual TUI."""
    from pychronicle.validation import validate_target_file
    val_res = validate_target_file(target)
    if not val_res.is_valid:
        click.secho(f"Validation Failed:\n{val_res.error_message}", fg="red", bold=True)
        sys.exit(1)

    config = ChronicleConfig(db_path=db_path, verbose=verbose)
    storage = SQLiteStorage(db_path=db_path)
    try:
        result = run_debug_session(target_path=target, config=config, storage=storage)
    except PyChronicleError as e:
        click.secho(f"\nDebugger Error: {e}", fg="red", bold=True)
        sys.exit(1)

    if result.replay:
        from pychronicle.tui import PyChronicleTUI
        app = PyChronicleTUI(replay=result.replay, source_file=target, watch_vars=list(watch_vars))
        app.run()


@cli.command(name="validate")
@click.argument("target", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def validate_cmd(target: Path) -> None:
    """Validate target file syntax, AST parsing, and readability without running."""
    from pychronicle.validation import validate_target_file
    val_res = validate_target_file(target)
    if val_res.is_valid:
        click.secho(f"[PASS] Validation Passed: '{target}'", fg="green", bold=True)
        click.echo(f"  Lines of Code: {val_res.line_count}")
        click.echo(f"  AST Nodes:     {val_res.ast_nodes_count}")
    else:
        click.secho(f"[FAIL] Validation Failed: '{target}'", fg="red", bold=True)
        click.echo(val_res.error_message)
        sys.exit(1)



@cli.command(name="history")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=DEFAULT_DB_PATH, help="Path to SQLite database.")
@click.pass_context
def history_cmd(ctx: click.Context, db_path: Path) -> None:
    """List all recorded debug sessions."""
    ctx.forward(sessions)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].endswith(".py") and not sys.argv[1].startswith("-") and Path(sys.argv[1]).exists():
        sys.argv.insert(1, "run")
    cli()



"""PyChronicle Textual Terminal User Interface (TUI).

Interactive terminal dashboard for time-travel debugging: timeline stepping,
source code line tracking, multi-scope variable inspection, and delta visualization.
"""

from pathlib import Path
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Header, Label, Static

from pychronicle.replay import ReconstructedState, ReplayEngine
from pychronicle.app import PyChronicleApp, launch_application


class PyChronicleTUI(App):
    """Textual interactive dashboard for PyChronicle time-travel debugging."""

    CSS = """
    Screen {
        background: #12141a;
        color: #e2e8f0;
    }

    #app-grid {
        layout: horizontal;
        height: 1fr;
        padding: 0 1;
    }

    #timeline-panel {
        width: 35%;
        border: round #3b82f6;
        background: #181b24;
        padding: 0 1;
        margin: 0 1 0 0;
    }

    #right-panel {
        width: 65%;
        layout: vertical;
    }

    #source-panel {
        height: 40%;
        border: round #10b981;
        background: #181b24;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    #watch-panel {
        height: 20%;
        border: round #f59e0b;
        background: #181b24;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    #state-panel {
        height: 40%;
        border: round #8b5cf6;
        background: #181b24;
        padding: 0 1;
    }

    .panel-title {
        text-style: bold;
        color: #60a5fa;
        padding: 0 0 1 0;
        border-bottom: solid #2d3748;
    }

    .state-title {
        color: #a78bfa;
    }

    .source-title {
        color: #34d399;
    }

    .watch-title {
        color: #fbbf24;
    }

    #timeline-table {
        height: 1fr;
    }

    #source-content {
        height: 1fr;
    }

    #watch-content {
        height: 1fr;
    }

    #state-content {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("left", "prev_step", "Prev Step", priority=True),
        Binding("p", "prev_step", "Prev Step"),
        Binding("right", "next_step", "Next Step", priority=True),
        Binding("n", "next_step", "Next Step"),
        Binding("home", "first_step", "First Step"),
        Binding("end", "last_step", "Last Step"),
        Binding("w", "toggle_watch_active", "Watch Active"),
        Binding("c", "clear_watches", "Clear Watches"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        replay: ReplayEngine,
        source_file: Optional[Path | str] = None,
        watch_vars: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self.replay = replay
        self.source_path = Path(source_file) if source_file else Path(replay.session_info["filename"])
        self.source_lines: List[str] = []
        if self.source_path.exists():
            try:
                self.source_lines = self.source_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                self.source_lines = ["<Error loading source code>"]

        self.watch_vars: List[str] = list(watch_vars or [])
        self.current_step_num: int = 1
        self.total_steps: int = self.replay.total_steps

    def compose(self) -> ComposeResult:
        """Create child widgets for the TUI."""
        yield Header(show_clock=True)
        with Horizontal(id="app-grid"):
            with Vertical(id="timeline-panel"):
                yield Label(
                    f"TIMELINE (Session #{self.replay.session_id} - {self.total_steps} Steps)",
                    classes="panel-title",
                )
                yield DataTable(id="timeline-table", cursor_type="row")

            with Vertical(id="right-panel"):
                with Vertical(id="source-panel"):
                    yield Label(
                        f"SOURCE: {self.source_path.name}",
                        classes="panel-title source-title",
                        id="source-title-label",
                    )
                    with VerticalScroll(id="source-content"):
                        yield Static(id="source-view", expand=True)

                with Vertical(id="watch-panel"):
                    yield Label("WATCH VARIABLES [w: Watch Active | c: Clear]", classes="panel-title watch-title")
                    with VerticalScroll(id="watch-content"):
                        yield Static(id="watch-view", expand=True)

                with Vertical(id="state-panel"):
                    yield Label("RECONSTRUCTED STATE", classes="panel-title state-title")
                    with VerticalScroll(id="state-content"):
                        yield Static(id="state-view", expand=True)

    def on_mount(self) -> None:
        """Initialize widgets when TUI mounts."""
        self.title = f"PyChronicle Time-Travel Debugger — {self.source_path.name}"
        table = self.query_one("#timeline-table", DataTable)
        table.add_columns("Step", "Line", "Event", "Scope", "Changes")

        timeline = self.replay.get_timeline()
        for item in timeline:
            marker = "*" if item["has_changes"] else ""
            if item["has_exception"]:
                marker = "! EXC"
            elif item["has_return"]:
                marker = "< RET"
            table.add_row(
                f"{item['step']:03d}",
                f"{item['line']:03d}" if item["line"] else "-",
                item["event"],
                item["scope"],
                marker,
            )

        if self.total_steps > 0:
            self.show_step(1)

    def show_step(self, step_num: int) -> None:
        """Update source, watch, state, and timeline for the given step number."""
        if self.total_steps == 0:
            return

        self.current_step_num = max(1, min(step_num, self.total_steps))
        state: ReconstructedState = self.replay.state_at(self.current_step_num)

        try:
            if not self._screen_stack:
                return
        except Exception:
            return

        # Update DataTable cursor
        table = self.query_one("#timeline-table", DataTable)
        try:
            table.move_cursor(row=self.current_step_num - 1)
        except Exception:
            pass

        # Update Source View
        source_static = self.query_one("#source-view", Static)
        source_markup = []
        for idx, line_text in enumerate(self.source_lines, 1):
            if idx == state.line:
                source_markup.append(
                    f"[bold yellow]▶ {idx:3d} | {line_text}[/bold yellow]"
                )
            else:
                source_markup.append(
                    f"[dim]{idx:3d} |[/dim] {line_text}"
                )
        source_static.update("\n".join(source_markup) if source_markup else "<Empty Source>")

        # Update Watch Variables View
        watch_static = self.query_one("#watch-view", Static)
        watch_markup = []
        if self.watch_vars:
            watch_values = self.replay.get_watch_values_at(self.current_step_num, self.watch_vars)
            for var in self.watch_vars:
                val = watch_values.get(var)
                val_repr = "[dim red]<undefined>[/dim red]" if val is None else f"[bold cyan]{val}[/bold cyan]"
                change = state.changes.get(var)
                if change:
                    op = change.get("operation", "CHANGE")
                    marker = f" [bold yellow]({op})[/bold yellow]"
                else:
                    marker = ""
                watch_markup.append(f"  [bold yellow][W] {var}[/bold yellow] = {val_repr}{marker}")
        else:
            watch_markup.append("  [dim](No active watches. Press 'w' to watch active scope variables, or pass -w <var>)[/dim]")
        watch_static.update("\n".join(watch_markup))

        # Update State Inspector
        state_static = self.query_one("#state-view", Static)
        state_markup = []

        # Step header info
        state_markup.append(
            f"[bold cyan]Step {state.step}/{self.total_steps}[/bold cyan] | "
            f"Line: [bold white]{state.line}[/bold white] | "
            f"Event: [bold green]{state.event}[/bold green] | "
            f"Active Scope: [bold magenta]{state.active_scope}[/bold magenta]"
        )

        if state.return_value is not None:
            state_markup.append(f"[bold yellow]⮑ Return Value:[/bold yellow] [green]{state.return_value}[/green]")

        if state.exception_info is not None:
            state_markup.append(f"[bold red]⚠ Exception:[/bold red] [bold red]{state.exception_info}[/bold red]")

        state_markup.append("\n[bold underline]Step Deltas:[/bold underline]")
        if state.changes:
            for v_name, chg in state.changes.items():
                op = chg.get("operation")
                old_v = chg.get("old", "null")
                new_v = chg.get("new", "null")
                if op == "CREATE":
                    state_markup.append(f"  [green]+ {v_name}[/green]: [dim]null[/dim] -> [bold]{new_v}[/bold]")
                elif op == "UPDATE":
                    state_markup.append(f"  [yellow]~ {v_name}[/yellow]: [dim]{old_v}[/dim] -> [bold]{new_v}[/bold]")
                elif op == "DELETE":
                    state_markup.append(f"  [red]- {v_name}[/red]: [dim]{old_v}[/dim] -> [dim red]DELETED[/dim red]")
        else:
            state_markup.append("  [dim](No variable changes in this step)[/dim]")

        state_markup.append("\n[bold underline]Reconstructed Scopes:[/bold underline]")
        for s_name, s_vars in state.scopes.items():
            is_active = (s_name == state.active_scope)
            scope_prefix = "[bold magenta]● Scope: " if is_active else "[dim]○ Scope: "
            scope_suffix = " (ACTIVE)[/bold magenta]" if is_active else "[/dim]"
            state_markup.append(f"{scope_prefix}{s_name}{scope_suffix}")
            if s_vars:
                for k, v in s_vars.items():
                    color = "bold white" if is_active else "dim"
                    state_markup.append(f"    [{color}]{k}[/{color}] = [cyan]{v}[/cyan]")
            else:
                state_markup.append("    [dim]<empty namespace>[/dim]")

        state_static.update("\n".join(state_markup))

    def action_next_step(self) -> None:
        """Go forward one step."""
        if self.current_step_num < self.total_steps:
            self.show_step(self.current_step_num + 1)

    def action_prev_step(self) -> None:
        """Go backward one step."""
        if self.current_step_num > 1:
            self.show_step(self.current_step_num - 1)

    def action_first_step(self) -> None:
        """Jump to first step."""
        self.show_step(1)

    def action_last_step(self) -> None:
        """Jump to last step."""
        self.show_step(self.total_steps)

    def action_toggle_watch_active(self) -> None:
        """Add active scope variables to watch list."""
        if self.total_steps > 0:
            state = self.replay.state_at(self.current_step_num)
            for v_name in state.active_variables.keys():
                if v_name not in self.watch_vars:
                    self.watch_vars.append(v_name)
            self.show_step(self.current_step_num)

    def action_clear_watches(self) -> None:
        """Clear all watch variables."""
        self.watch_vars.clear()
        self.show_step(self.current_step_num)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Sync when user selects a row directly in the timeline table."""
        step_idx = event.cursor_row + 1
        self.show_step(step_idx)

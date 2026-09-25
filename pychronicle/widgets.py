"""PyChronicle Modular Textual TUI Widgets.

Contains reusable UI widgets:
- SourceCodePanel: Numbered, read-only source code view with active execution line highlighting.
- VariablesPanel: Reconstructed multi-scope variable inspector and step delta visualizer.
- TimelineControl: Interactive execution timeline scrubber and step indicator.
- WatchPanel: Watched variable tracker across historical execution steps.
- ControlsBar: Bottom navigation toolbar with hotkey legends.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static

from pychronicle.replay import ReconstructedState, ReplayEngine


class SourceCodePanel(Vertical):
    """Numbered, syntax-highlighted source code panel with active execution line indicator."""

    DEFAULT_CSS = """
    SourceCodePanel {
        height: 1fr;
        border: round #10b981;
        background: #181b24;
        padding: 0 1;
    }
    .panel-header {
        text-style: bold;
        color: #34d399;
        padding-bottom: 1;
        border-bottom: solid #2d3748;
    }
    #source-scroll {
        height: 1fr;
    }
    """

    def __init__(self, filename: str, source_code: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.filename = filename
        self.lines = source_code.splitlines() if source_code else ["<Empty Source>"]
        self.current_line: Optional[int] = None

    def compose(self) -> ComposeResult:
        yield Label(f"SOURCE: {Path(self.filename).name}", classes="panel-header", id="source-header-label")
        with VerticalScroll(id="source-scroll"):
            yield Static(id="source-code-content", expand=True)

    def set_active_line(self, lineno: Optional[int]) -> None:
        """Update source code view with highlighted active execution line."""
        self.current_line = lineno
        markup_lines: List[str] = []
        for idx, line_text in enumerate(self.lines, start=1):
            if lineno is not None and idx == lineno:
                markup_lines.append(f"[bold black on #34d399] ▶ {idx:3d} │ {line_text} [/bold black on #34d399]")
            else:
                markup_lines.append(f"[dim]{idx:3d} │[/dim] {line_text}")

        content_widget = self.query_one("#source-code-content", Static)
        content_widget.update("\n".join(markup_lines))


class VariablesPanel(Vertical):
    """Multi-scope variable inspector and step delta visualizer."""

    DEFAULT_CSS = """
    VariablesPanel {
        height: 1fr;
        border: round #8b5cf6;
        background: #181b24;
        padding: 0 1;
    }
    .var-header {
        text-style: bold;
        color: #a78bfa;
        padding-bottom: 1;
        border-bottom: solid #2d3748;
    }
    #vars-scroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("VARIABLES & RECONSTRUCTED STATE", classes="var-header")
        with VerticalScroll(id="vars-scroll"):
            yield Static(id="vars-content", expand=True)

    def update_state(self, state: ReconstructedState, total_steps: int) -> None:
        """Render reconstructed variables, active scope, and step deltas."""
        markup: List[str] = []

        markup.append(
            f"[bold cyan]Step {state.step}/{total_steps}[/bold cyan] │ "
            f"Line: [bold white]{state.line or '-'}[/bold white] │ "
            f"Event: [bold green]{state.event}[/bold green] │ "
            f"Scope: [bold magenta]{state.active_scope}[/bold magenta]"
        )

        if state.return_value is not None:
            markup.append(f"[bold yellow]⮑ Return Value:[/bold yellow] [green]{state.return_value}[/green]")

        if state.exception_info is not None:
            markup.append(f"[bold red]⚠ Exception:[/bold red] [bold red]{state.exception_info}[/bold red]")

        # Delta transitions in current step
        markup.append("\n[bold underline]Variable Transitions (Delta):[/bold underline]")
        if state.changes:
            for v_name, chg in state.changes.items():
                op = chg.get("operation")
                old_v = chg.get("old", "None")
                new_v = chg.get("new", "None")
                if op == "CREATE":
                    markup.append(f"  [green]+ {v_name}[/green]: [dim]None[/dim] ➔ [bold green]{new_v}[/bold green]")
                elif op == "UPDATE":
                    markup.append(f"  [yellow]~ {v_name}[/yellow]: [dim]{old_v}[/dim] ➔ [bold yellow]{new_v}[/bold yellow]")
                elif op == "DELETE":
                    markup.append(f"  [red]- {v_name}[/red]: [dim]{old_v}[/dim] ➔ [dim red]<deleted>[/dim red]")
        else:
            markup.append("  [dim](No variable changes in this step)[/dim]")

        # Scoped variable dictionary
        markup.append("\n[bold underline]Scoped Variables:[/bold underline]")
        for s_name, s_vars in state.scopes.items():
            is_active = (s_name == state.active_scope)
            bullet = "[bold magenta]● Scope:" if is_active else "[dim]○ Scope:"
            suffix = " (ACTIVE)[/bold magenta]" if is_active else "[/dim]"
            markup.append(f"{bullet} {s_name}{suffix}")
            if s_vars:
                for k, v in s_vars.items():
                    val_color = "bold cyan" if is_active else "dim"
                    markup.append(f"    {k} = [{val_color}]{v}[/{val_color}]")
            else:
                markup.append("    [dim]<empty>[/dim]")

        content_widget = self.query_one("#vars-content", Static)
        content_widget.update("\n".join(markup))


class TimelineControl(Vertical):
    """Visual timeline scrubber and step selector."""

    DEFAULT_CSS = """
    TimelineControl {
        height: auto;
        border: round #3b82f6;
        background: #181b24;
        padding: 0 1;
    }
    .timeline-header {
        text-style: bold;
        color: #60a5fa;
        padding-bottom: 1;
        border-bottom: solid #2d3748;
    }
    #timeline-visual {
        margin: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("EXECUTION TIMELINE (Time-Scrubbing)", classes="timeline-header", id="timeline-header-label")
        yield Static(id="timeline-visual", expand=True)

    def render_timeline(self, current_step: int, total_steps: int, timeline_data: List[Dict]) -> None:
        """Render ASCII/styled scrubber representation of the execution timeline."""
        if total_steps == 0:
            self.query_one("#timeline-visual", Static).update("[dim]No execution steps recorded.[/dim]")
            return

        # Build timeline string
        visible_window = 15
        start_step = max(1, current_step - visible_window // 2)
        end_step = min(total_steps, start_step + visible_window - 1)
        if end_step - start_step < visible_window:
            start_step = max(1, end_step - visible_window + 1)

        nodes: List[str] = []
        for s in range(start_step, end_step + 1):
            has_chg = timeline_data[s - 1].get("has_changes", False) if s - 1 < len(timeline_data) else False
            if s == current_step:
                nodes.append(f"[bold black on #3b82f6] [STEP {s}] [/bold black on #3b82f6]")
            elif has_chg:
                nodes.append(f"[bold cyan]({s})[/bold cyan]")
            else:
                nodes.append(f"[dim]{s}[/dim]")

        scrubber = " ── ".join(nodes)
        progress_pct = int((current_step / max(total_steps, 1)) * 100)
        status_line = f"[bold cyan]Step {current_step} of {total_steps}[/bold cyan] ({progress_pct}%) [dim]│ Left/Right/h/l: Scrub │ Space: Play/Pause │ r: Reset[/dim]"

        self.query_one("#timeline-visual", Static).update(f"{scrubber}\n\n{status_line}")


class WatchPanel(Vertical):
    """Watched variables panel tracking values and changes across execution history."""

    DEFAULT_CSS = """
    WatchPanel {
        height: auto;
        min-height: 5;
        border: round #f59e0b;
        background: #181b24;
        padding: 0 1;
    }
    .watch-header {
        text-style: bold;
        color: #fbbf24;
        padding-bottom: 1;
        border-bottom: solid #2d3748;
    }
    #watch-content {
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("WATCH VARIABLES [w: Watch Active | u: Unwatch | c: Clear]", classes="watch-header")
        with VerticalScroll(id="watch-scroll"):
            yield Static(id="watch-content", expand=True)

    def update_watches(
        self,
        watch_vars: List[str],
        current_step: int,
        replay: ReplayEngine,
        state: ReconstructedState,
    ) -> None:
        """Update watch variable display with current values and recent history."""
        if not watch_vars:
            msg = "[dim](No variables watched. Press 'w' to watch active variables, or run with -w <var>)[/dim]"
            self.query_one("#watch-content", Static).update(msg)
            return

        markup: List[str] = []
        watch_vals = replay.get_watch_values_at(current_step, watch_vars)

        for var in watch_vars:
            val = watch_vals.get(var)
            val_repr = "[dim red]<undefined>[/dim red]" if val is None else f"[bold cyan]{val}[/bold cyan]"
            chg = state.changes.get(var)
            chg_badge = f" [bold yellow]({chg.get('operation')})[/bold yellow]" if chg else ""

            # Fetch step history for this variable
            var_history = replay.get_variable_history(var)
            history_snippets = []
            for h in var_history:
                if h["step"] <= current_step and h["value"] is not None:
                    history_snippets.append(str(h["value"]))

            progression = " ➔ ".join(history_snippets[-5:]) if history_snippets else str(val)
            markup.append(f"  [bold yellow]👁 {var}[/bold yellow] = {val_repr}{chg_badge}  [dim](History: {progression})[/dim]")

        self.query_one("#watch-content", Static).update("\n".join(markup))

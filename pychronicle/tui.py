"""PyChronicle Textual Terminal User Interface (TUI).

Interactive terminal dashboard for time-travel debugging: timeline stepping,
source code line tracking, multi-scope variable inspection, and delta visualization.
"""

from pathlib import Path
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Label, Static

from pychronicle.app import PyChronicleApp, launch_application
from pychronicle.replay import ReconstructedState, ReplayEngine
from pychronicle.widgets import SourceCodePanel, TimelineControl, VariablesPanel, WatchPanel


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

    #left-panel {
        width: 35%;
        layout: vertical;
        margin-right: 1;
    }

    #timeline-panel {
        height: 1fr;
        border: round #3b82f6;
        background: #181b24;
        padding: 0 1;
    }

    #right-panel {
        width: 65%;
        layout: vertical;
    }

    #source-panel-box {
        height: 40%;
        margin-bottom: 1;
    }

    #watch-panel-box {
        height: 20%;
        margin-bottom: 1;
    }

    #state-panel-box {
        height: 40%;
    }

    .panel-title {
        text-style: bold;
        color: #60a5fa;
        padding: 0 0 1 0;
        border-bottom: solid #2d3748;
    }

    #timeline-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("left", "prev_step", "Prev Step", priority=True),
        Binding("h", "prev_step", "Prev Step"),
        Binding("p", "prev_step", "Prev Step"),
        Binding("right", "next_step", "Next Step", priority=True),
        Binding("l", "next_step", "Next Step"),
        Binding("n", "next_step", "Next Step"),
        Binding("space", "toggle_play_pause", "Play/Pause"),
        Binding("r", "reset_step", "Reset"),
        Binding("home", "first_step", "First Step"),
        Binding("end", "last_step", "Last Step"),
        Binding("w", "toggle_watch_active", "Watch Active"),
        Binding("u", "unwatch_last", "Unwatch"),
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
        self.source_code = ""
        if self.source_path.exists():
            try:
                self.source_code = self.source_path.read_text(encoding="utf-8")
            except Exception:
                self.source_code = "<Error loading source code>"

        self.watch_vars: List[str] = list(watch_vars or [])
        self.current_step_num: int = 1
        self.total_steps: int = self.replay.total_steps
        self.is_playing: bool = False
        self._play_timer = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the TUI."""
        yield Header(show_clock=True)
        with Horizontal(id="app-grid"):
            with Vertical(id="left-panel"):
                with Vertical(id="timeline-panel"):
                    yield Label(
                        f"TIMELINE (Session #{self.replay.session_id} - {self.total_steps} Steps)",
                        classes="panel-title",
                    )
                    yield DataTable(id="timeline-table", cursor_type="row")
                yield TimelineControl(id="timeline-scrubber-widget")

            with Vertical(id="right-panel"):
                yield SourceCodePanel(
                    filename=str(self.source_path),
                    source_code=self.source_code,
                    id="source-panel-box",
                )
                yield WatchPanel(id="watch-panel-box")
                yield VariablesPanel(id="state-panel-box")
        yield Footer()

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
        state: ReconstructedState = self.replay.get_state_at_step(self.current_step_num)

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
        try:
            source_panel = self.query_one("#source-panel-box", SourceCodePanel)
            source_panel.set_active_line(state.line)
        except Exception:
            pass

        # Update Watch Variables View
        try:
            watch_panel = self.query_one("#watch-panel-box", WatchPanel)
            watch_panel.update_watches(self.watch_vars, self.current_step_num, self.replay, state)
        except Exception:
            pass

        # Update Variables and Delta Inspector
        try:
            vars_panel = self.query_one("#state-panel-box", VariablesPanel)
            vars_panel.update_state(state, self.total_steps)
        except Exception:
            pass

        # Update Timeline Scrubber
        try:
            timeline_ctrl = self.query_one("#timeline-scrubber-widget", TimelineControl)
            timeline_ctrl.render_timeline(self.current_step_num, self.total_steps, self.replay.get_timeline())
        except Exception:
            pass

    def action_next_step(self) -> None:
        """Go forward one step without re-executing code."""
        if self.current_step_num < self.total_steps:
            self.show_step(self.current_step_num + 1)
        elif self.is_playing:
            self.action_toggle_play_pause()

    def action_prev_step(self) -> None:
        """Go backward one step without re-executing code."""
        if self.current_step_num > 1:
            self.show_step(self.current_step_num - 1)

    def action_first_step(self) -> None:
        """Jump to first step."""
        self.show_step(1)

    def action_last_step(self) -> None:
        """Jump to last step."""
        self.show_step(self.total_steps)

    def action_reset_step(self) -> None:
        """Reset timeline position to Step 1."""
        self.show_step(1)

    def action_toggle_play_pause(self) -> None:
        """Toggle automatic timeline playback."""
        self.is_playing = not self.is_playing
        if self.is_playing:
            if self.current_step_num >= self.total_steps:
                self.show_step(1)
            self._play_timer = self.set_interval(0.8, self._autoplay_tick)
            self.notify("Playback Started (Space to Pause)")
        else:
            if self._play_timer:
                self._play_timer.stop()
                self._play_timer = None
            self.notify("Playback Paused")

    def _autoplay_tick(self) -> None:
        if self.is_playing:
            if self.current_step_num < self.total_steps:
                self.action_next_step()
            else:
                self.action_toggle_play_pause()

    def action_toggle_watch_active(self) -> None:
        """Add active scope variables to watch list."""
        if self.total_steps > 0:
            state = self.replay.get_state_at_step(self.current_step_num)
            added = []
            for v_name in state.active_variables.keys():
                if v_name not in self.watch_vars:
                    self.watch_vars.append(v_name)
                    added.append(v_name)
            if added:
                self.notify(f"Watching: {', '.join(added)}")
            self.show_step(self.current_step_num)

    def action_unwatch_last(self) -> None:
        """Remove the last watched variable."""
        if self.watch_vars:
            removed = self.watch_vars.pop()
            self.notify(f"Unwatched: {removed}")
            self.show_step(self.current_step_num)

    def action_clear_watches(self) -> None:
        """Clear all watch variables."""
        self.watch_vars.clear()
        self.notify("Cleared all watched variables")
        self.show_step(self.current_step_num)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Sync when user selects a row directly in the timeline table."""
        step_idx = event.cursor_row + 1
        self.show_step(step_idx)

"""PyChronicle Interactive Developer Workspace Application (TUI).

Full-featured developer IDE application with three core modes:
1. Programming Workspace (Default): Sidebar program list, editable code editor, bottom output console.
2. History Workspace: Searchable ledger of past program executions with status badges.
3. Historical Execution View: Immutable source snapshot (READ-ONLY), stored output (zero rerun), and time-travel replay.
4. Debug Mode: Focused side-by-side debugging with active line highlight (▶), variables table, watch list, and compact timeline.
"""

from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Header,
    Input,
    Label,
    OptionList,
    Static,
    TextArea,
)
from textual.widgets.option_list import Option

from pychronicle.application import ApplicationService
from pychronicle.config import DEFAULT_DB_PATH
from pychronicle.replay import ReconstructedState, ReplayEngine


class NewProgramModal(ModalScreen[Optional[str]]):
    """Modal dialog to enter a new program name."""

    CSS = """
    NewProgramModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #new-modal-box {
        width: 60;
        height: auto;
        border: thick #3b82f6;
        background: #181b24;
        padding: 1 2;
    }

    #new-modal-title {
        text-style: bold;
        color: #60a5fa;
        margin-bottom: 1;
    }

    #new-modal-input {
        margin-bottom: 1;
        background: #0f1117;
        border: solid #3b82f6;
    }

    #new-modal-buttons {
        layout: horizontal;
        align: right middle;
    }

    #new-modal-buttons Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="new-modal-box"):
            yield Label("Create New Program", id="new-modal-title")
            yield Input(placeholder="e.g. 5 Digit Palindrome", id="new-modal-input")
            with Horizontal(id="new-modal-buttons"):
                yield Button("Cancel", id="btn-modal-cancel", variant="error")
                yield Button("Create", id="btn-modal-create", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-modal-create":
            input_val = self.query_one("#new-modal-input", Input).value.strip()
            self.dismiss(input_val if input_val else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_val = event.value.strip()
        self.dismiss(input_val if input_val else None)


class UnsavedQuitModal(ModalScreen[str]):
    """Modal dialog asking user to Save & Quit, Quit Without Saving, or Cancel."""

    CSS = """
    UnsavedQuitModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #unsaved-modal-box {
        width: 60;
        height: auto;
        border: thick #ea580c;
        background: #181b24;
        padding: 1 2;
    }

    #unsaved-modal-title {
        text-style: bold;
        color: #f97316;
        margin-bottom: 1;
    }

    #unsaved-modal-msg {
        margin-bottom: 1;
        color: #e2e8f0;
    }

    #unsaved-modal-buttons {
        layout: horizontal;
        align: right middle;
    }

    #unsaved-modal-buttons Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="unsaved-modal-box"):
            yield Label("Unsaved Changes", id="unsaved-modal-title")
            yield Label("You have unsaved changes. Choose an action before quitting:", id="unsaved-modal-msg")
            with Horizontal(id="unsaved-modal-buttons"):
                yield Button("Cancel", id="btn-unsaved-cancel", variant="default")
                yield Button("Quit Without Saving", id="btn-unsaved-discard", variant="error")
                yield Button("Save & Quit", id="btn-unsaved-save", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-unsaved-save":
            self.dismiss("save")
        elif event.button.id == "btn-unsaved-discard":
            self.dismiss("discard")
        else:
            self.dismiss("cancel")


class PyChronicleApp(App):
    """PyChronicle Terminal User Interface Application."""

    TITLE = "PyChronicle — Developer Time-Travel Workspace"
    SUB_TITLE = "Programming Workspace • History • Debugger"

    CSS = """
    Screen {
        background: #0f1117;
        color: #e2e8f0;
    }

    /* Navigation Bar */
    #nav-bar {
        height: 3;
        background: #181b24;
        border-bottom: solid #2d3748;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    .nav-btn {
        margin-right: 1;
        height: 3;
        min-width: 7;
        padding: 0 1;
    }

    #btn-nav-home {
        background: #1e3a8a;
        color: #ffffff;
    }

    #btn-nav-save {
    }

    #btn-nav-run {
        background: #15803d;
        color: #ffffff;
    }

    #btn-nav-debug {
        background: #b45309;
        color: #ffffff;
    }

    #btn-nav-history {
        background: #2563eb;
        color: #ffffff;
    }

    #btn-nav-back, .btn-nav-back {
        background: #ca8a04;
        color: #ffffff;
        border: none;
    }

    #btn-nav-quit, .btn-nav-quit {
        background: #ea580c;
        color: #ffffff;
        border: none;
    }

    #nav-status-label {
        width: 1fr;
        min-width: 0;
        color: #94a3b8;
        text-style: bold;
        height: 3;
        content-align: left middle;
        margin-left: 1;
        margin-right: 1;
    }

    #nav-right-group {
        width: auto;
        height: 3;
        layout: horizontal;
        align: right middle;
    }

    /* Main View Switcher */
    #main-switcher {
        height: 1fr;
    }

    /* ========================================================================= */
    /* 1. WORKSPACE VIEW                                                        */
    /* ========================================================================= */
    #view-workspace {
        layout: horizontal;
        height: 1fr;
        padding: 0 1;
    }

    #workspace-sidebar {
        width: 32;
        border-right: solid #2d3748;
        background: #13161f;
        padding: 0 1;
    }

    #sidebar-title {
        text-style: bold;
        color: #60a5fa;
        padding: 1 0 0 0;
    }

    #search-programs-input {
        margin: 1 0;
        background: #0f1117;
        border: solid #374151;
        height: 3;
    }

    #btn-new-program {
        width: 100%;
        margin-bottom: 1;
    }

    #programs-list {
        height: 1fr;
        background: #13161f;
        border: none;
    }

    #workspace-editor-column {
        width: 1fr;
        layout: vertical;
        padding-left: 1;
    }

    #editor-header-bar {
        height: 2;
        layout: horizontal;
        align: left middle;
        background: #181b24;
        padding: 0 1;
        border-bottom: solid #2d3748;
    }

    #active-prog-name {
        text-style: bold;
        color: #38bdf8;
    }

    #active-prog-version {
        color: #a78bfa;
        margin-left: 2;
    }

    #active-prog-status {
        margin-left: 2;
        color: #4ade80;
    }

    #code-editor {
        height: 60%;
        background: #0b0d13;
        border: solid #1e293b;
    }

    #output-pane {
        height: 40%;
        border-top: solid #2d3748;
        background: #10131a;
        padding: 0 1;
        layout: vertical;
    }

    #output-header-bar {
        height: 2;
        layout: horizontal;
        align: left middle;
        border-bottom: solid #1f2937;
    }

    #output-title {
        text-style: bold;
        color: #fbbf24;
    }

    #output-metrics {
        margin-left: 2;
        color: #94a3b8;
    }

    #output-content-scroll {
        height: 1fr;
    }

    #output-content {
        padding: 0;
        color: #f1f5f9;
    }

    /* ========================================================================= */
    /* 2. HISTORY VIEW                                                          */
    /* ========================================================================= */
    #view-history {
        layout: vertical;
        height: 1fr;
        padding: 1 2;
    }

    #history-header-bar {
        height: 3;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    #history-title {
        text-style: bold;
        color: #f59e0b;
        margin-left: 2;
    }

    #search-history-input {
        margin-bottom: 1;
        background: #181b24;
        border: solid #374151;
        height: 3;
    }

    #history-table {
        height: 1fr;
        border: solid #2d3748;
        background: #13161f;
    }

    /* ========================================================================= */
    /* 3. HISTORICAL READ ONLY VIEW                                             */
    /* ========================================================================= */
    #view-historical-run {
        layout: vertical;
        height: 1fr;
        padding: 0 1;
    }

    #hist-banner {
        height: 3;
        background: #1e1b4b;
        border-bottom: solid #4338ca;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    #hist-banner-title {
        text-style: bold;
        color: #c7d2fe;
        margin-left: 2;
    }

    #hist-content-grid {
        height: 1fr;
        layout: horizontal;
    }

    #hist-source-pane {
        width: 50%;
        border-right: solid #2d3748;
        background: #0f1117;
        padding: 0 1;
        layout: vertical;
    }

    #hist-output-pane {
        width: 50%;
        background: #13161f;
        padding: 0 1;
        layout: vertical;
    }

    #hist-step-bar {
        height: 3;
        background: #181b24;
        border-top: solid #2d3748;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    /* ========================================================================= */
    /* 4. DEBUG VIEW                                                            */
    /* ========================================================================= */
    #view-debug {
        layout: vertical;
        height: 1fr;
        padding: 0 1;
    }

    #debug-header {
        height: 3;
        background: #1e293b;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
        border-bottom: solid #334155;
    }

    #debug-title-label {
        text-style: bold;
        color: #38bdf8;
        margin-left: 2;
    }

    #debug-grid {
        height: 1fr;
        layout: horizontal;
    }

    #debug-source-panel {
        width: 55%;
        border-right: solid #2d3748;
        background: #0f1117;
        padding: 0 1;
        layout: vertical;
    }

    #debug-vars-panel {
        width: 45%;
        background: #13161f;
        padding: 0 1;
        layout: vertical;
    }

    #debug-watch-strip {
        height: 3;
        background: #1e1b4b;
        border-top: solid #3730a3;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    #debug-scrubber-bar {
        height: 3;
        background: #181b24;
        border-top: solid #2d3748;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    .scrub-btn {
        margin-right: 1;
        height: 3;
        min-width: 9;
        padding: 0 1;
        background: #2563eb;
        color: #ffffff;
        text-style: bold;
        border: none;
    }

    .scrub-btn:hover {
        background: #3b82f6;
    }

    Button.scrub-btn:disabled {
        background: #1e3a8a;
        color: #93c5fd;
    }

    #btn-debug-first, #btn-hist-first {
        background: #1d4ed8;
        color: #ffffff;
    }

    #btn-debug-prev, #btn-hist-prev {
        background: #2563eb;
        color: #ffffff;
    }

    #btn-debug-next, #btn-hist-next {
        background: #3b82f6;
        color: #ffffff;
        text-style: bold;
    }

    #btn-debug-last, #btn-hist-last {
        background: #1d4ed8;
        color: #ffffff;
    }

    #debug-step-badge, #hist-step-badge {
        color: #60a5fa;
        text-style: bold;
        margin-left: 2;
        height: 3;
        content-align: left middle;
    }

    .panel-header-label {
        text-style: bold;
        color: #94a3b8;
        padding: 0 0 1 0;
        border-bottom: solid #2d3748;
    }
    """

    BINDINGS = [
        Binding("h", "navigate_home", "Home"),
        Binding("f1", "navigate_home", "Workspace", priority=True),
        Binding("f2", "switch_view('history')", "History", priority=True),
        Binding("f3", "switch_view('debug')", "Debug", priority=True),
        Binding("f5", "run_active_program", "Run", priority=True),
        Binding("ctrl+s", "save_active_program", "Save", priority=True),
        Binding("ctrl+n", "create_new_program", "New Program", priority=True),
        Binding("ctrl+enter", "run_active_program", "Run", priority=True),
        Binding("escape", "handle_escape", "Cancel/Exit", priority=True),
        Binding("q", "safe_quit", "Quit"),
        Binding("ctrl+q", "safe_quit", "Quit", priority=True),
        Binding("f10", "step_next", "Step Next", priority=True),
        Binding("shift+f10", "step_prev", "Step Prev", priority=True),
        Binding("home", "step_first", "First Step"),
        Binding("end", "step_last", "Last Step"),
        Binding("w", "add_watch_interactive", "Watch Active"),
        Binding("c", "clear_watches", "Clear Watches"),
    ]

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        service: Optional[ApplicationService] = None,
    ) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.service = service or ApplicationService(db_path=self.db_path, seed_demo=True)
        self.active_program_id: Optional[int] = None
        self.active_program: Optional[Dict[str, Any]] = None
        self.current_execution: Optional[Dict[str, Any]] = None
        self.historical_execution: Optional[Dict[str, Any]] = None
        self.historical_replay: Optional[ReplayEngine] = None
        self.debug_replay: Optional[ReplayEngine] = None
        self.debug_step: int = 1
        self.debug_total_steps: int = 1
        self.hist_step: int = 1
        self.hist_total_steps: int = 1
        self.watch_vars: List[str] = ["num", "original", "reverse", "temp", "digit", "result"]
        self.programs_cache: List[Dict[str, Any]] = []
        self.previous_view: str = "workspace"

    def compose(self) -> ComposeResult:
        """Compose top-level layout with persistent navigation bar and content switcher."""
        yield Header(show_clock=True)

        with Horizontal(id="nav-bar"):
            yield Button("🏠 Home (H)", id="btn-nav-home", classes="nav-btn", variant="primary")
            yield Button("Save (Ctrl+S)", id="btn-nav-save", classes="nav-btn", variant="default")
            yield Button("▶ Run (F5)", id="btn-nav-run", classes="nav-btn", variant="success")
            yield Button("🐞 Debug (F3)", id="btn-nav-debug", classes="nav-btn", variant="warning")
            yield Button("History (F2)", id="btn-nav-history", classes="nav-btn", variant="default")
            yield Label("PyChronicle Workspace Ready", id="nav-status-label")
            with Horizontal(id="nav-right-group"):
                yield Button("✕ Quit (Q)", id="btn-nav-quit", classes="nav-btn btn-nav-quit")

        with ContentSwitcher(initial="view-workspace", id="main-switcher"):
            # 1. PROGRAMMING WORKSPACE (DEFAULT)
            with Horizontal(id="view-workspace"):
                with Vertical(id="workspace-sidebar"):
                    yield Label("PROGRAMS", id="sidebar-title")
                    yield Input(placeholder="🔍 Search...", id="search-programs-input")
                    yield Button("+ New Program (Ctrl+N)", id="btn-new-program", variant="primary")
                    yield OptionList(id="programs-list")

                with Vertical(id="workspace-editor-column"):
                    with Horizontal(id="editor-header-bar"):
                        yield Label("📄 Loading...", id="active-prog-name")
                        yield Label("v1", id="active-prog-version")
                        yield Label("NEVER_RUN", id="active-prog-status")
                    yield TextArea.code_editor("", language="python", id="code-editor")
                    with Vertical(id="output-pane"):
                        with Horizontal(id="output-header-bar"):
                            yield Label("OUTPUT CONSOLE", id="output-title")
                            yield Label("Status: Ready", id="output-metrics")
                        with VerticalScroll(id="output-content-scroll"):
                            yield Static("Ready. Press F5 or click 'Run' to execute.", id="output-content")

            # 2. HISTORY VIEW
            with Vertical(id="view-history"):
                with Horizontal(id="history-header-bar"):
                    yield Label("EXECUTION HISTORY LEDGER", id="history-title")
                yield Input(placeholder="🔍 Search historical runs...", id="search-history-input")
                yield DataTable(id="history-table", cursor_type="row")

            # 3. HISTORICAL READ ONLY VIEW
            with Vertical(id="view-historical-run"):
                with Horizontal(id="hist-banner"):
                    yield Label("🔒 READ ONLY — HISTORICAL EXECUTION", id="hist-banner-title")
                    yield Button("📋 Copy to Workspace", id="btn-hist-copy", classes="nav-btn", variant="success")
                with Horizontal(id="hist-content-grid"):
                    with Vertical(id="hist-source-pane"):
                        yield Label("IMMUTABLE SOURCE SNAPSHOT", classes="panel-header-label")
                        yield TextArea.code_editor("", language="python", read_only=True, id="hist-source-code")
                    with Vertical(id="hist-output-pane"):
                        yield Label("STORED EXECUTION OUTPUT & VARIABLES", classes="panel-header-label")
                        with VerticalScroll():
                            yield Static(id="hist-output-content")
                with Horizontal(id="hist-step-bar"):
                    yield Button("⏮ First", id="btn-hist-first", classes="scrub-btn")
                    yield Button("◀ Prev", id="btn-hist-prev", classes="scrub-btn")
                    yield Button("▶ Next", id="btn-hist-next", classes="scrub-btn")
                    yield Button("⏭ Last", id="btn-hist-last", classes="scrub-btn")
                    yield Label("Step 1 / 1", id="hist-step-badge")

            # 4. FOCUSED DEBUG VIEW
            with Vertical(id="view-debug"):
                with Horizontal(id="debug-header"):
                    yield Label("🐞 DEBUG MODE", id="debug-title-label")
                with Horizontal(id="debug-grid"):
                    with Vertical(id="debug-source-panel"):
                        yield Label("SOURCE EXECUTION TRACKING", classes="panel-header-label", id="debug-source-header")
                        with VerticalScroll():
                            yield Static(id="debug-source-view")
                    with Vertical(id="debug-vars-panel"):
                        yield Label("CURRENT STEP VARIABLES", classes="panel-header-label")
                        with VerticalScroll():
                            yield Static(id="debug-vars-view")
                with Horizontal(id="debug-watch-strip"):
                    yield Label("WATCH: [w: Watch Active | c: Clear]", id="debug-watch-label")
                    yield Static(id="debug-watch-view")
                with Horizontal(id="debug-scrubber-bar"):
                    yield Button("⏮ First", id="btn-debug-first", classes="scrub-btn")
                    yield Button("◀ Prev", id="btn-debug-prev", classes="scrub-btn")
                    yield Button("▶ Next", id="btn-debug-next", classes="scrub-btn")
                    yield Button("⏭ Last", id="btn-debug-last", classes="scrub-btn")
                    yield Label("Step 1 / 1", id="debug-step-badge")

    def on_mount(self) -> None:
        """Initialize workspace and load initial programs upon startup."""
        self.load_programs_list()
        self.action_switch_view("workspace")

    # =========================================================================
    # View State Management
    # =========================================================================

    def action_navigate_home(self) -> None:
        """Centralized global Home navigation action returning to the Programming Workspace."""
        self.action_switch_view("workspace")
        self.set_nav_status("Returned to Programming Workspace")

    def action_switch_view(self, view_name: str) -> None:
        """Switch active view state and adapt top toolbar buttons."""
        switcher = self.query_one("#main-switcher", ContentSwitcher)
        cur = switcher.current
        if cur and cur.startswith("view-"):
            clean_cur = cur.replace("view-", "")
            if clean_cur != view_name:
                self.previous_view = clean_cur

        target_id = f"view-{view_name}"
        switcher.current = target_id

        # Update navigation buttons state per view requirements
        try:
            home_btn = self.query_one("#btn-nav-home", Button)
            save_btn = self.query_one("#btn-nav-save", Button)
            run_btn = self.query_one("#btn-nav-run", Button)
            debug_btn = self.query_one("#btn-nav-debug", Button)
            hist_btn = self.query_one("#btn-nav-history", Button)

            if view_name == "workspace":
                home_btn.display = True
                home_btn.variant = "primary"
                save_btn.display = True
                run_btn.display = True
                debug_btn.display = True
                debug_btn.variant = "warning"
                hist_btn.display = True
                hist_btn.variant = "default"
            elif view_name == "debug":
                home_btn.display = True
                home_btn.variant = "primary"
                save_btn.display = False
                run_btn.display = False
                debug_btn.display = False
                hist_btn.display = False
            elif view_name == "history":
                home_btn.display = True
                home_btn.variant = "primary"
                save_btn.display = False
                run_btn.display = False
                debug_btn.display = False
                hist_btn.display = False
            elif view_name == "historical-run":
                home_btn.display = True
                home_btn.variant = "primary"
                save_btn.display = False
                run_btn.display = False
                debug_btn.display = False
                hist_btn.display = False
        except Exception:
            pass

        if view_name == "history":
            self.load_history_table()
        elif view_name == "debug":
            if not self.debug_replay and self.active_program_id:
                self.action_run_active_program(open_debug=True)
            elif self.debug_replay:
                self.render_debug_step()

    def action_handle_escape(self) -> None:
        """Handle Escape key / Back button contextually returning to previous view."""
        switcher = self.query_one("#main-switcher", ContentSwitcher)
        if switcher.current == "view-historical-run":
            self.action_switch_view("history")
        elif switcher.current == "view-debug":
            prev = self.previous_view if self.previous_view in ("workspace", "history") else "workspace"
            self.action_switch_view(prev)
        elif switcher.current == "view-history":
            self.action_navigate_home()
        elif switcher.current == "view-workspace":
            self.set_nav_status("Already at Programming Workspace")

    def has_unsaved_changes(self) -> bool:
        """Check if current editor text differs from the active program's saved source."""
        if not self.active_program_id or not self.active_program:
            return False
        try:
            editor = self.query_one("#code-editor", TextArea)
            return editor.text != self.active_program.get("source_code", "")
        except Exception:
            return False

    def action_safe_quit(self) -> None:
        """Quit the application cleanly, prompting if unsaved changes exist."""
        if self.has_unsaved_changes():
            def on_modal_result(result: Optional[str]) -> None:
                if result == "save":
                    self.action_save_active_program()
                    self.exit()
                elif result == "discard":
                    self.exit()
                # 'cancel' or None dismisses dialog and stays in app

            self.push_screen(UnsavedQuitModal(), on_modal_result)
        else:
            self.exit()

    # =========================================================================
    # Program Management & Workspace
    # =========================================================================

    def load_programs_list(self, filter_query: Optional[str] = None) -> None:
        """Populate the sidebar with saved programs."""
        progs = self.service.list_programs(search_query=filter_query)
        self.programs_cache = progs
        opt_list = self.query_one("#programs-list", OptionList)
        opt_list.clear_options()

        if not progs:
            opt_list.add_option(Option("<No programs found>", id="none", disabled=True))
            return

        selected_idx = 0
        for idx, p in enumerate(progs):
            status = p.get("last_status") or "NEVER_RUN"
            icon = "●" if status == "SUCCESS" else ("▲" if "ERROR" in status else "○")
            label = f"{icon} {p['name']} (v{p.get('version_count', 1)})"
            opt_list.add_option(Option(label, id=str(p["id"])))
            if self.active_program_id == p["id"]:
                selected_idx = idx

        if progs:
            target_prog = progs[selected_idx]
            self.load_program_into_editor(target_prog["id"])
            opt_list.highlighted = selected_idx

    def load_program_into_editor(self, program_id: int) -> None:
        """Load a program's source code and metadata into the editor."""
        prog = self.service.get_program(program_id)
        if not prog:
            return

        self.active_program_id = prog["id"]
        self.active_program = prog

        self.query_one("#active-prog-name", Label).update(f"📄 {prog['name']}")
        self.query_one("#active-prog-version", Label).update(f"v{prog.get('version_count', 1)}")
        st = prog.get("last_status") or "NEVER_RUN"
        self.query_one("#active-prog-status", Label).update(f"Status: {st}")

        editor = self.query_one("#code-editor", TextArea)
        editor.text = prog["source_code"]
        self.set_nav_status(f"Loaded '{prog['name']}'")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Switch active program when sidebar item is selected."""
        if event.option_id and event.option_id != "none":
            self.load_program_into_editor(int(event.option_id))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter programs or history on input change."""
        if event.input.id == "search-programs-input":
            self.load_programs_list(filter_query=event.value.strip() or None)
        elif event.input.id == "search-history-input":
            self.load_history_table(filter_query=event.value.strip() or None)

    def action_create_new_program(self) -> None:
        """Open the create new program modal."""
        def on_modal_result(name: Optional[str]) -> None:
            if name:
                try:
                    default_code = 'num = 12321\nprint("Number:", num)\n'
                    created = self.service.create_program(name=name, source_code=default_code)
                    self.load_programs_list()
                    self.load_program_into_editor(created["id"])
                    self.set_nav_status(f"Created program '{created['name']}'")
                except Exception as e:
                    self.set_nav_status(f"Error: {e}")

        self.push_screen(NewProgramModal(), on_modal_result)

    def action_save_active_program(self) -> None:
        """Save the code editor content to the active program."""
        if not self.active_program_id:
            return

        editor = self.query_one("#code-editor", TextArea)
        code = editor.text

        try:
            updated = self.service.update_program(
                program_id=self.active_program_id,
                source_code=code,
            )
            self.active_program = updated
            self.query_one("#active-prog-version", Label).update(f"v{updated.get('version_count', 1)}")
            self.set_nav_status(f"Saved '{updated['name']}' (v{updated.get('version_count', 1)})")
        except Exception as e:
            self.set_nav_status(f"Save error: {e}")

    def action_run_active_program(self, open_debug: bool = False) -> None:
        """Execute the active program via canonical tracer backend and display output."""
        if not self.active_program_id:
            return

        # Save code before running
        editor = self.query_one("#code-editor", TextArea)
        code = editor.text
        try:
            self.service.update_program(program_id=self.active_program_id, source_code=code)
        except Exception:
            pass

        self.set_nav_status("Executing program...")
        try:
            res = self.service.run_program(
                program_id=self.active_program_id,
                source_override=code,
                watch_vars=self.watch_vars,
            )
            self.current_execution = res
            status = res["status"]
            dur = res["duration_ms"]
            steps = res["total_steps"]

            # Update Workspace Output Pane
            self.query_one("#output-metrics", Label).update(
                f"Status: {status} • Time: {dur} ms • Steps: {steps}"
            )
            out_content = self.query_one("#output-content", Static)
            out_text = res["stdout"] if res["stdout"] else "(No stdout output)"
            if res["stderr"]:
                out_text += f"\n\n[STDERR / ERROR]\n{res['stderr']}"
            out_content.update(out_text)

            # Update program status
            self.query_one("#active-prog-status", Label).update(f"Status: {status}")

            # Prepare debug replay if session exists
            if res.get("session_id") and steps > 0:
                self.debug_replay = ReplayEngine(session_id=res["session_id"], storage=self.service.storage)
                self.debug_total_steps = steps
                self.debug_step = 1

            if open_debug:
                self.action_switch_view("debug")
            else:
                self.set_nav_status(f"Run Finished: {status} ({dur} ms)")

        except Exception as e:
            self.query_one("#output-content", Static).update(f"Execution Error: {e}")
            self.set_nav_status(f"Execution Error: {e}")

    # =========================================================================
    # History & Historical Read-Only View
    # =========================================================================

    def load_history_table(self, filter_query: Optional[str] = None) -> None:
        """Load cross-program execution records into the history table."""
        runs = self.service.list_all_executions(search_query=filter_query)
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Run ID", "Program", "Status", "Duration", "Steps", "Started At")

        for r in runs:
            st = r["status"]
            dur_str = f"{r['duration_ms']:.1f} ms" if r["duration_ms"] is not None else "-"
            prog_title = f"{r['program_name']} — Run #{r['id']}"
            table.add_row(
                f"#{r['id']}",
                prog_title,
                st,
                dur_str,
                str(r["step_count"] or 0),
                r["started_at"][:19] if r["started_at"] else "-",
                key=str(r["id"]),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open historical execution when a history row is selected."""
        if event.data_table.id == "history-table":
            if event.row_key and event.row_key.value:
                exec_id = int(event.row_key.value)
                self.open_historical_execution(exec_id)

    def open_historical_execution(self, execution_id: int) -> None:
        """Load and display an immutable historical execution."""
        record = self.service.get_execution(execution_id)
        if not record:
            return

        self.historical_execution = record
        self.query_one("#hist-banner-title", Label).update(
            f"🔒 READ ONLY — {record['program_name']} — Run #{record['id']} ({record['status']})"
        )

        # 1. Immutable Source Snapshot (READ ONLY)
        hist_editor = self.query_one("#hist-source-code", TextArea)
        hist_editor.text = record["source_snapshot"]

        # 2. Setup historical replay
        if record.get("debug_session_id"):
            try:
                self.historical_replay = ReplayEngine(
                    session_id=record["debug_session_id"],
                    storage=self.service.storage,
                )
                self.hist_total_steps = self.historical_replay.total_steps
                self.hist_step = 1
            except Exception:
                self.historical_replay = None
                self.hist_total_steps = 1
                self.hist_step = 1
        else:
            self.historical_replay = None
            self.hist_total_steps = 1
            self.hist_step = 1

        self.render_historical_step()
        self.action_switch_view("historical-run")

    def render_historical_step(self) -> None:
        """Render historical execution output, state, and metrics at the selected step."""
        record = self.historical_execution
        if not record:
            return

        output_static = self.query_one("#hist-output-content", Static)
        badge = self.query_one("#hist-step-badge", Label)
        badge.update(f"Step {self.hist_step} / {self.hist_total_steps}")

        markup = []
        markup.append(f"[bold yellow]=== STORED OUTPUT ===[/bold yellow]")
        markup.append(record["stdout"] if record["stdout"] else "<No stdout output>")
        if record["stderr"]:
            markup.append(f"\n[bold red]Stored Error:[/bold red] {record['stderr']}")

        markup.append(f"\n[bold cyan]Execution Details:[/bold cyan]")
        markup.append(f"• Duration: {record['duration_ms']} ms")
        markup.append(f"• Started: {record['started_at']}")
        markup.append(f"• Total Steps: {self.hist_total_steps}")

        if self.historical_replay and self.hist_total_steps > 0:
            state = self.historical_replay.state_at(self.hist_step)
            markup.append(f"\n[bold green]Reconstructed State (Step {state.step} | Line {state.line}):[/bold green]")
            if state.active_variables:
                for k, v in state.active_variables.items():
                    markup.append(f"  [bold]{k}[/bold] = [cyan]{v}[/cyan]")
            else:
                markup.append("  [dim]<No variables in active scope>[/dim]")

        output_static.update("\n".join(markup))
        try:
            self.query_one("#btn-hist-first", Button).disabled = (self.hist_step <= 1)
            self.query_one("#btn-hist-prev", Button).disabled = (self.hist_step <= 1)
            self.query_one("#btn-hist-next", Button).disabled = (self.hist_step >= self.hist_total_steps)
            self.query_one("#btn-hist-last", Button).disabled = (self.hist_step >= self.hist_total_steps)
        except Exception:
            pass

    def action_copy_historical_to_workspace(self) -> None:
        """Duplicate historical execution source into a new editable program."""
        if not self.historical_execution:
            return

        exec_id = self.historical_execution["id"]
        try:
            copied = self.service.copy_execution_to_workspace(exec_id)
            self.load_programs_list()
            self.load_program_into_editor(copied["id"])
            self.action_switch_view("workspace")
            self.set_nav_status(f"Copied historical run to workspace as '{copied['name']}'")
        except Exception as e:
            self.set_nav_status(f"Copy Error: {e}")

    # =========================================================================
    # Debug Mode & Stepping
    # =========================================================================

    def render_debug_step(self) -> None:
        """Render source code, variables, and deltas in focused debug mode."""
        if not self.debug_replay or self.debug_total_steps == 0:
            self.query_one("#debug-source-view", Static).update("<No debug session active>")
            self.query_one("#debug-vars-view", Static).update("<No variables>")
            return

        state = self.debug_replay.state_at(self.debug_step)
        self.query_one("#debug-step-badge", Label).update(f"Step {self.debug_step} / {self.debug_total_steps}")
        self.query_one("#debug-source-header", Label).update(f"SOURCE (Line {state.line or '-'})")

        try:
            self.query_one("#btn-debug-first", Button).disabled = (self.debug_step <= 1)
            self.query_one("#btn-debug-prev", Button).disabled = (self.debug_step <= 1)
            self.query_one("#btn-debug-next", Button).disabled = (self.debug_step >= self.debug_total_steps)
            self.query_one("#btn-debug-last", Button).disabled = (self.debug_step >= self.debug_total_steps)
        except Exception:
            pass

        # 1. Render Source with active line indicator ▶
        prog_code = self.active_program["source_code"] if self.active_program else ""
        source_lines = prog_code.splitlines()
        source_markup = []
        for idx, line in enumerate(source_lines, 1):
            if idx == state.line:
                source_markup.append(f"[bold yellow]▶ {idx:3d} | {line}[/bold yellow]")
            else:
                source_markup.append(f"[dim]{idx:3d} |[/dim] {line}")
        self.query_one("#debug-source-view", Static).update("\n".join(source_markup) if source_markup else "<Empty Source>")

        # 2. Render Current Step Variables
        vars_markup = []
        vars_markup.append(f"[bold cyan]Scope: {state.active_scope}[/bold cyan] | Event: [green]{state.event}[/green]\n")

        if state.changes:
            vars_markup.append("[bold underline]Step Deltas:[/bold underline]")
            for k, chg in state.changes.items():
                op = chg.get("operation")
                new_v = chg.get("new")
                old_v = chg.get("old")
                if op == "CREATE":
                    vars_markup.append(f"  [green]+ {k}[/green] = [bold]{new_v}[/bold]")
                elif op == "UPDATE":
                    vars_markup.append(f"  [yellow]~ {k}[/yellow] = [bold]{new_v}[/bold] [dim](was {old_v})[/dim]")
                elif op == "DELETE":
                    vars_markup.append(f"  [red]- {k}[/red] [dim red]DELETED[/dim red]")
            vars_markup.append("")

        vars_markup.append("[bold underline]Active Variables:[/bold underline]")
        if state.active_variables:
            for k, v in state.active_variables.items():
                vars_markup.append(f"  [bold white]{k}[/bold white] = [cyan]{v}[/cyan]")
        else:
            vars_markup.append("  [dim]<No variables in active scope>[/dim]")

        self.query_one("#debug-vars-view", Static).update("\n".join(vars_markup))

        # 3. Render Watch Variables
        watch_markup = []
        watch_vals = self.debug_replay.get_watch_values_at(self.debug_step, self.watch_vars)
        for var in self.watch_vars:
            val = watch_vals.get(var)
            if val is not None:
                watch_markup.append(f"[yellow]{var}[/yellow]=[cyan]{val}[/cyan]")
        self.query_one("#debug-watch-view", Static).update(" • ".join(watch_markup) if watch_markup else "[dim]No active watches matched[/dim]")

    def action_step_next(self) -> None:
        """Step forward one step in debug or historical view."""
        switcher = self.query_one("#main-switcher", ContentSwitcher)
        if switcher.current == "view-debug" and self.debug_step < self.debug_total_steps:
            self.debug_step += 1
            self.render_debug_step()
        elif switcher.current == "view-historical-run" and self.hist_step < self.hist_total_steps:
            self.hist_step += 1
            self.render_historical_step()

    def action_step_prev(self) -> None:
        """Step backward one step in debug or historical view."""
        switcher = self.query_one("#main-switcher", ContentSwitcher)
        if switcher.current == "view-debug" and self.debug_step > 1:
            self.debug_step -= 1
            self.render_debug_step()
        elif switcher.current == "view-historical-run" and self.hist_step > 1:
            self.hist_step -= 1
            self.render_historical_step()

    def action_step_first(self) -> None:
        """Jump to first step in debug or historical view."""
        switcher = self.query_one("#main-switcher", ContentSwitcher)
        if switcher.current == "view-debug":
            self.debug_step = 1
            self.render_debug_step()
        elif switcher.current == "view-historical-run":
            self.hist_step = 1
            self.render_historical_step()

    def action_step_last(self) -> None:
        """Jump to last step in debug or historical view."""
        switcher = self.query_one("#main-switcher", ContentSwitcher)
        if switcher.current == "view-debug":
            self.debug_step = self.debug_total_steps
            self.render_debug_step()
        elif switcher.current == "view-historical-run":
            self.hist_step = self.hist_total_steps
            self.render_historical_step()

    def action_add_watch_interactive(self) -> None:
        """Add active scope variables to watch list."""
        if self.debug_replay and self.debug_total_steps > 0:
            state = self.debug_replay.state_at(self.debug_step)
            for var in state.active_variables.keys():
                if var not in self.watch_vars:
                    self.watch_vars.append(var)
            self.render_debug_step()

    def action_clear_watches(self) -> None:
        """Clear all watch variables."""
        self.watch_vars.clear()
        self.render_debug_step()

    # =========================================================================
    # Button Click Router
    # =========================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click events across views."""
        btn_id = event.button.id
        if btn_id == "btn-nav-home":
            self.action_navigate_home()
        elif btn_id == "btn-nav-save":
            self.action_save_active_program()
        elif btn_id == "btn-nav-run":
            self.action_run_active_program(open_debug=False)
        elif btn_id == "btn-nav-debug":
            self.action_run_active_program(open_debug=True)
        elif btn_id == "btn-nav-history":
            self.action_switch_view("history")
        elif btn_id == "btn-nav-quit":
            self.action_safe_quit()
        elif btn_id in ("btn-new-program", "btn-nav-new"):
            self.action_create_new_program()
        elif btn_id == "btn-hist-copy":
            self.action_copy_historical_to_workspace()
        elif btn_id in ("btn-debug-first", "btn-hist-first"):
            self.action_step_first()
        elif btn_id in ("btn-debug-prev", "btn-hist-prev"):
            self.action_step_prev()
        elif btn_id in ("btn-debug-next", "btn-hist-next"):
            self.action_step_next()
        elif btn_id in ("btn-debug-last", "btn-hist-last"):
            self.action_step_last()

    def set_nav_status(self, text: str) -> None:
        """Update top navigation status bar."""
        self.query_one("#nav-status-label", Label).update(text)


def launch_application(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Launch the PyChronicle Developer Workspace TUI."""
    app = PyChronicleApp(db_path=db_path)
    app.run()

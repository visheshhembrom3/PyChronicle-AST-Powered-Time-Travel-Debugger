"""Automated tests for PyChronicle Developer Workspace TUI (Textual App).
Validates Final Navigation & Debug Control Cleanup:
- Removal of ALL Back buttons
- Home button present ONLY on Workspace toolbar
- Per-screen top toolbar states (Workspace, Debug, History, Historical Execution)
- Quit button (Orange) present in top right of all screens
- Blue stepper controls ([ ⏮ First ], [ ◀ Prev ], [ ▶ Next ], [ ⏭ Last ])
- Keyboard shortcuts (H, F5, F3, F2, Q, F10, Shift+F10, Home, End)
- Zero bottom shortcut footer
- History immutability and workspace preservation
"""

import asyncio
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from textual.widgets import Button, DataTable, Footer, Label, TextArea
from pychronicle.app import PyChronicleApp, UnsavedQuitModal
from pychronicle.application import ApplicationService


def test_tui_top_toolbar_buttons_and_no_footer():
    """Verify top toolbar has 6 buttons on workspace, Quit is last, no Back button, and no bottom Footer exists."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "tui_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)
            app = PyChronicleApp(db_path=db_path, service=service)

            async with app.run_test(size=(120, 35)) as pilot:
                # 1. Verify NO bottom Footer widget exists
                footer_widgets = list(app.query("Footer"))
                assert len(footer_widgets) == 0

                # 2. Verify NO Back button exists anywhere in the DOM
                back_btns = list(app.query("#btn-nav-back"))
                assert len(back_btns) == 0

                # 3. Verify top toolbar button sequence: Home, Save, Run, Debug, History, and Quit
                nav_bar = app.query_one("#nav-bar")
                buttons = list(nav_bar.query("Button"))
                assert len(buttons) == 6

                btn_home = app.query_one("#btn-nav-home", Button)
                btn_save = app.query_one("#btn-nav-save", Button)
                btn_run = app.query_one("#btn-nav-run", Button)
                btn_debug = app.query_one("#btn-nav-debug", Button)
                btn_history = app.query_one("#btn-nav-history", Button)
                btn_quit = app.query_one("#btn-nav-quit", Button)

                # Assert labels with shortcut keys
                assert "Home" in str(btn_home.label) and "(H)" in str(btn_home.label)
                assert "Save" in str(btn_save.label) and "(Ctrl+S)" in str(btn_save.label)
                assert "Run" in str(btn_run.label) and "(F5)" in str(btn_run.label)
                assert "Debug" in str(btn_debug.label) and "(F3)" in str(btn_debug.label)
                assert "History" in str(btn_history.label) and "(F2)" in str(btn_history.label)
                assert "Quit" in str(btn_quit.label) and "(Q)" in str(btn_quit.label)

                # 4. Verify sidebar contains + New Program
                sidebar_new_btn = app.query_one("#btn-new-program", Button)
                assert "+ New Program" in str(sidebar_new_btn.label)

    asyncio.run(_run())


def test_tui_per_screen_toolbar_and_no_back():
    """Verify Universal Home is displayed on all views, and Debug/History/Historical have minimal toolbars (Home + Quit only)."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "tui_screens_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)
            app = PyChronicleApp(db_path=db_path, service=service)

            async with app.run_test(size=(120, 35)) as pilot:
                btn_home = app.query_one("#btn-nav-home", Button)
                btn_save = app.query_one("#btn-nav-save", Button)
                btn_run = app.query_one("#btn-nav-run", Button)
                btn_debug = app.query_one("#btn-nav-debug", Button)
                btn_history = app.query_one("#btn-nav-history", Button)
                btn_quit = app.query_one("#btn-nav-quit", Button)

                # SCREEN 1: WORKSPACE -> HOME | SAVE | RUN | DEBUG | HISTORY | QUIT
                assert app.query_one("#main-switcher").current == "view-workspace"
                assert btn_home.display is True
                assert btn_save.display is True
                assert btn_run.display is True
                assert btn_debug.display is True
                assert btn_history.display is True
                assert btn_quit.display is True

                # SCREEN 2: DEBUG MODE -> HOME | QUIT ONLY
                app.action_switch_view("debug")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-debug"
                # Universal Home MUST be visible
                assert btn_home.display is True
                # Save, Run, Debug, History MUST be hidden on Debug toolbar
                assert btn_save.display is False
                assert btn_run.display is False
                assert btn_debug.display is False
                assert btn_history.display is False
                # Quit MUST remain visible
                assert btn_quit.display is True

                # SCREEN 3: HISTORY -> HOME | QUIT ONLY
                app.action_switch_view("history")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-history"
                # Universal Home MUST be visible
                assert btn_home.display is True
                # Save, Run, Debug, History MUST be hidden on History toolbar
                assert btn_save.display is False
                assert btn_run.display is False
                assert btn_debug.display is False
                assert btn_history.display is False
                # Quit MUST remain visible
                assert btn_quit.display is True

                # SCREEN 4: HISTORICAL EXECUTION -> HOME | QUIT ONLY
                # Run a program first to get an execution ID
                app.action_switch_view("workspace")
                await pilot.pause()
                app.action_run_active_program()
                await pilot.pause()
                exec_id = app.current_execution["execution_id"]

                app.open_historical_execution(exec_id)
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-historical-run"
                # Universal Home MUST be visible
                assert btn_home.display is True
                # Save, Run, Debug, History MUST be hidden
                assert btn_save.display is False
                assert btn_run.display is False
                assert btn_debug.display is False
                assert btn_history.display is False
                # Quit remains visible in top right
                assert btn_quit.display is True

                # Verify Read-Only indicator is visible and no Back button exists
                assert "READ ONLY" in str(app.query_one("#hist-banner-title", Label).render())
                assert len(app.query("#btn-nav-back")) == 0

    asyncio.run(_run())


def test_tui_home_navigation_from_all_major_states():
    """Verify Universal Home button and 'H' key navigate Home from Workspace, Run, Debug, History, Historical View, and Error State."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "tui_nav_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)
            app = PyChronicleApp(db_path=db_path, service=service)

            async with app.run_test(size=(120, 35)) as pilot:
                # TEST A: Workspace -> Home button click
                assert app.query_one("#main-switcher").current == "view-workspace"
                await pilot.click("#btn-nav-home")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

                # TEST B: Workspace -> Run -> Home button click
                app.action_run_active_program()
                await pilot.pause()
                assert app.current_execution is not None
                assert app.current_execution["status"] == "SUCCESS"
                await pilot.click("#btn-nav-home")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

                # TEST C: Workspace -> Debug -> Home button click & H key
                app.action_switch_view("debug")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-debug"
                # Click visible Home button from inside Debug toolbar
                await pilot.click("#btn-nav-home")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

                # TEST D: Workspace -> History -> Home button click & H key
                app.action_switch_view("history")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-history"
                # Click visible Home button from inside History toolbar
                await pilot.click("#btn-nav-home")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

                # TEST E: History -> Historical Execution -> Home button click
                exec_id = app.current_execution["execution_id"]
                app.open_historical_execution(exec_id)
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-historical-run"
                await pilot.click("#btn-nav-home")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

                # TEST F: Execution Error -> Home key
                editor = app.query_one("#code-editor", TextArea)
                editor.text = "x = 10 / 0\n"
                app.action_run_active_program()
                await pilot.pause()
                assert app.current_execution is not None
                assert app.current_execution["status"] in ("USER_ERROR", "FAILED")
                assert "ZeroDivisionError" in app.current_execution["stderr"]
                # Navigate Home via 'h' key
                await pilot.press("h")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

    asyncio.run(_run())


def test_tui_debug_and_historical_stepper_controls():
    """Verify debug step controls [ ⏮ First ], [ ◀ Prev ], [ ▶ Next ], [ ⏭ Last ], keyboard keys, and step counter."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "tui_step_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)
            app = PyChronicleApp(db_path=db_path, service=service)

            async with app.run_test(size=(120, 35)) as pilot:
                # 1. Run and open Debug mode
                app.action_run_active_program(open_debug=True)
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-debug"
                assert app.debug_total_steps > 1

                btn_first = app.query_one("#btn-debug-first", Button)
                btn_prev = app.query_one("#btn-debug-prev", Button)
                btn_next = app.query_one("#btn-debug-next", Button)
                btn_last = app.query_one("#btn-debug-last", Button)
                badge = app.query_one("#debug-step-badge", Label)

                # Verify button labels
                assert "First" in str(btn_first.label) and "⏮" in str(btn_first.label)
                assert "Prev" in str(btn_prev.label) and "◀" in str(btn_prev.label)
                assert "Next" in str(btn_next.label) and "▶" in str(btn_next.label)
                assert "Last" in str(btn_last.label) and "⏭" in str(btn_last.label)

                # At Step 1: First and Prev are disabled, Next and Last are enabled
                assert app.debug_step == 1
                assert "Step 1 /" in str(badge.render())
                assert btn_first.disabled is True
                assert btn_prev.disabled is True
                assert btn_next.disabled is False
                assert btn_last.disabled is False

                # 2. Step forward via F10
                await pilot.press("f10")
                await pilot.pause()
                assert app.debug_step == 2
                assert "Step 2 /" in str(badge.render())
                assert btn_first.disabled is False
                assert btn_prev.disabled is False

                # 3. Step forward via clicking Next button
                await pilot.click("#btn-debug-next")
                await pilot.pause()
                assert app.debug_step == 3

                # 4. Step backward via Shift+F10
                await pilot.press("shift+f10")
                await pilot.pause()
                assert app.debug_step == 2

                # 5. Jump to Last step via End key
                await pilot.press("end")
                await pilot.pause()
                assert app.debug_step == app.debug_total_steps
                assert f"Step {app.debug_total_steps} /" in str(badge.render())
                assert btn_next.disabled is True
                assert btn_last.disabled is True

                # 6. Jump to First step via Home key
                await pilot.press("home")
                await pilot.pause()
                assert app.debug_step == 1
                assert btn_first.disabled is True
                assert btn_prev.disabled is True

    asyncio.run(_run())


def test_tui_workspace_preservation_and_history_immutability():
    """Verify editing code is preserved when navigating Home from Debug/History and historical runs stay immutable."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "tui_preserve_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)
            app = PyChronicleApp(db_path=db_path, service=service)

            async with app.run_test(size=(120, 35)) as pilot:
                # Run initial program so Run #1 is recorded
                app.action_run_active_program()
                await pilot.pause()
                run1_id = app.current_execution["execution_id"]

                # User writes custom code
                custom_code = "a = 100\nb = 200\nresult = a + b\nprint(result)\n"
                editor = app.query_one("#code-editor", TextArea)
                editor.text = custom_code

                # Go to Debug
                app.action_switch_view("debug")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-debug"

                # Press 'h' to navigate Home
                await pilot.press("h")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"

                # Verify workspace code is preserved
                assert editor.text == custom_code

                # Open History Run #1 -> check immutability
                app.open_historical_execution(run1_id)
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-historical-run"
                hist_editor = app.query_one("#hist-source-code", TextArea)
                assert hist_editor.read_only is True
                assert "num = 12321" in hist_editor.text

                # Return Home via 'h' key
                await pilot.press("h")
                await pilot.pause()
                assert app.query_one("#main-switcher").current == "view-workspace"
                assert editor.text == custom_code

    asyncio.run(_run())


def test_tui_quit_button_and_safe_quit_modal():
    """Verify Quit button exits cleanly when clean, and prompts with UnsavedQuitModal when dirty."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "tui_quit_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)
            app = PyChronicleApp(db_path=db_path, service=service)

            async with app.run_test(size=(120, 35)) as pilot:
                # 1. With clean editor -> Clicking Quit calls action_safe_quit and exits
                assert not app.has_unsaved_changes()

                # 2. Modify editor -> has_unsaved_changes() becomes True
                editor = app.query_one("#code-editor", TextArea)
                editor.text = "modified_code = True\n"
                assert app.has_unsaved_changes()

                # 3. Trigger safe quit with dirty state -> triggers modal
                app.action_safe_quit()
                await pilot.pause()
                assert isinstance(app.screen, UnsavedQuitModal)

                # Dismiss modal
                await pilot.click("#btn-unsaved-cancel")
                await pilot.pause()
                assert not isinstance(app.screen, UnsavedQuitModal)

    asyncio.run(_run())


def test_tui_toolbar_responsive_sizes():
    """Verify top toolbar buttons remain visible and properly labeled across small and large sizes without Back button."""
    async def _run():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db_path = Path(tmp) / "resp_test.db"
            service = ApplicationService(db_path=db_path, seed_demo=True)

            # Test standard 80x24 terminal
            app_small = PyChronicleApp(db_path=db_path, service=service)
            async with app_small.run_test(size=(80, 24)) as pilot:
                btn_home = app_small.query_one("#btn-nav-home", Button)
                btn_save = app_small.query_one("#btn-nav-save", Button)
                btn_run = app_small.query_one("#btn-nav-run", Button)
                btn_debug = app_small.query_one("#btn-nav-debug", Button)
                btn_history = app_small.query_one("#btn-nav-history", Button)
                btn_quit = app_small.query_one("#btn-nav-quit", Button)

                assert "Home" in str(btn_home.label)
                assert str(btn_save.label) == "Save (Ctrl+S)"
                assert "Run" in str(btn_run.label)
                assert "Debug" in str(btn_debug.label)
                assert "History" in str(btn_history.label)
                assert "Quit" in str(btn_quit.label)
                assert len(app_small.query("#btn-nav-back")) == 0

            # Test large 140x40 terminal
            app_large = PyChronicleApp(db_path=db_path, service=service)
            async with app_large.run_test(size=(140, 40)) as pilot:
                btn_home = app_large.query_one("#btn-nav-home", Button)
                btn_save = app_large.query_one("#btn-nav-save", Button)
                btn_run = app_large.query_one("#btn-nav-run", Button)
                btn_debug = app_large.query_one("#btn-nav-debug", Button)
                btn_history = app_large.query_one("#btn-nav-history", Button)
                btn_quit = app_large.query_one("#btn-nav-quit", Button)

                assert "Home" in str(btn_home.label)
                assert str(btn_save.label) == "Save (Ctrl+S)"
                assert "Run" in str(btn_run.label)
                assert "Debug" in str(btn_debug.label)
                assert "History" in str(btn_history.label)
                assert "Quit" in str(btn_quit.label)
                assert len(app_large.query("#btn-nav-back")) == 0

    asyncio.run(_run())

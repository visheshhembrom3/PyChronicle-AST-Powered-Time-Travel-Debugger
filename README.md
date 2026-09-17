# PyChronicle — AST-Powered Python Time-Travel Debugger

PyChronicle is an AST-powered, time-travel debugger for Python. It instruments Python source code using the standard library `ast` module, tracks runtime execution events via `sys.settrace()`, captures differential state transitions across scopes, persists history efficiently in SQLite, and provides deterministic backwards-and-forwards state reconstruction through direct backend JSON execution, a rich CLI, and an interactive Textual TUI.

---

## 1. Architecture Overview

```
                    PyChronicle
                        │
             ┌──────────┴──────────┐
             │                     │
       CLI (main.py)          TUI (tui.py)
             │                     │
             └──────────┬──────────┘
                        │
                pychronicle.tracer
              (BACKEND ENTRY POINT)
                        │
                TracerBackend.execute()
                        │
                 AST Rewriter
                        │
                 Compile Program
                        │
                  sys.settrace()
                        │
                 Runtime Events
                        │
                 State Capture
                        │
                 Delta Generator
                        │
                  SQLite Storage
                        │
                 Replay Engine
                        │
            JSON Output to stdout (tracer.py)
```

### Architectural Principles
- **Tracer as Backend Entry Point**: `pychronicle/tracer.py` is the primary executable backend entry point. It owns the execution lifecycle (file reading, AST transformation, compilation, session creation, `sys.settrace` activation, `exec()` execution in isolated namespace, delta generation, and SQLite persistence).
- **JSON-First Terminal Interface**: Direct backend execution emits machine-readable JSON to `stdout` exclusively. All diagnostic logs are sent to `stderr` with `--debug`.
- **Presentation Layer Separation**: `main.py` (CLI) and `tui.py` (TUI) are lightweight presentation/controller layers that invoke `from pychronicle.tracer import run_debug_session`.
- **AST vs. Runtime Boundary**: AST rewriting performs non-intrusive source-level instrumentation (`__pychronicle_hook__`) and maintains line/branch metadata. `sys.settrace()` drives the execution engine to catch `call`, `line`, `return`, and `exception` events.
- **Deep Mutation Isolation**: In-place mutations (`list.append`, `dict[k]=v`) are snapshotted using deep cloning and SHA-256 fingerprinting so past time-travel states are never mutated retroactively.
- **Scoped State Namespaces**: Variables are partitioned by execution scope (`<module>`, functions, closures) rather than merged into a single flat dictionary.
- **Sparse Delta Storage**: Rather than dumping full memory dumps per step, only modified variables are saved with `CREATE`, `UPDATE`, and `DELETE` operations.

---

## 2. Requirements & Installation

- **Python Version**: Python 3.10+ (Tested on Python 3.14)
- **Core Dependencies**: `click`, `textual`, `pytest`, `rich`

### Installation

```bash
# Clone or navigate to the repository
cd Projetpython

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

---

## 3. Direct Backend & CLI Usage

### Direct Backend Execution (JSON Terminal Output)
```bash
# Execute target directly and output pure JSON to stdout
python -m pychronicle.tracer examples/demo.py

# Specify custom SQLite database path
python -m pychronicle.tracer examples/demo.py --db data/custom.db

# Enable diagnostic logs on stderr (stdout remains clean JSON)
python -m pychronicle.tracer examples/demo.py --debug
```

#### Sample JSON Output
```json
{
  "tool": "PyChronicle",
  "version": "0.1.0",
  "backend": "tracer.py",
  "execution": {
    "target": "examples/demo.py",
    "status": "SUCCESS",
    "session_id": 1,
    "steps": 36,
    "snapshots": 36,
    "started_at": "2026-09-15T20:58:28.683288",
    "finished_at": "2026-09-15T20:58:28.721063"
  },
  "trace": {
    "engine": "sys.settrace",
    "events": {
      "call": 3,
      "line": 30,
      "return": 3,
      "exception": 0
    }
  },
  "storage": {
    "database": "data/pychronicle.db"
  },
  "final_state": {
    "<module>": {
      "final_output": "{'total': 30, 'facts': [1, 2, 6, 24], 'flag': True}"
    }
  },
  "error": null
}
```

### CLI Commands (main.py)
```bash
# Execute target program via CLI (delegates to tracer.py)
python main.py debug examples/demo.py

# Launch the interactive Textual TUI directly after execution
python main.py debug examples/demo.py --tui

# List all recorded sessions
python main.py sessions

# Inspect a session summary and timeline
python main.py inspect 1

# Reconstruct historical state at step 27
python main.py replay 1 --step 27

# Walk step-by-step through execution history
python main.py replay 1

# Open interactive TUI for an existing recorded session
python main.py tui 1
```

---

## 4. Exit Codes

| Exit Code | Status | Meaning |
| :--- | :--- | :--- |
| **0** | `SUCCESS` | Program executed, traced, and recorded successfully. |
| **1** | `USER_ERROR` | User program threw an unhandled runtime exception (e.g. `ZeroDivisionError`). |
| **2** | `PYCHRONICLE_ERROR` | Syntax error, missing target file, or internal failure. |
| **3** | `CLI_ERROR` | Invalid or missing command line arguments. |

---

## 5. Textual Terminal User Interface (TUI)

PyChronicle features an interactive terminal user interface built with [Textual](https://textual.textualize.io/):

- **Timeline Panel (Left)**: Scrollable list of recorded steps with step numbers, line numbers, event types (`call`, `line`, `return`, `exception`), and active scopes.
- **Source Code Viewer (Top Right)**: Source code of the target program with the currently executing line highlighted in real-time.
- **Reconstructed State Inspector (Bottom Right)**: Dynamic view of all program variables grouped by scope, fine-grained delta transitions (`+ CREATE`, `~ UPDATE`, `- DELETE`), return values, and exception alerts.

### TUI Keybindings
- `←` or `P`: Step backward (Previous Step)
- `→` or `N`: Step forward (Next Step)
- `Home`: Jump to first step
- `End`: Jump to last step
- `Q`: Quit TUI

---

## 6. Automated Testing & Validation

```bash
# Run 44 unit, integration, CLI, and JSON tests
pytest tests/ -v

# Run 14 synthetic validation datasets
python validation/validation_runner.py

# Run performance benchmark
python benchmarks/benchmark.py
```

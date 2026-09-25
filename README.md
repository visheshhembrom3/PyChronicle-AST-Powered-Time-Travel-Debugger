# PyChronicle – AST-Powered Python Time-Travel Debugger

PyChronicle is an advanced, AST-powered time-travel debugger and programming workspace for Python. Traditional debuggers move unidirectionally forward through program execution; if a bug or subtle variable mutation occurred in the past, developers are forced to restart the process and step through from the beginning. 

PyChronicle records execution history using runtime differential delta state capture and SQLite persistence, enabling developers to scrub backward and forward through past program states **without re-running the target program**.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Problem Statement](#problem-statement)
3. [Novel Idea](#novel-idea)
4. [Key Modules](#key-modules)
5. [Architecture](#architecture)
6. [Project Structure](#project-structure)
7. [Installation](#installation)
8. [Running](#running)
9. [CLI (Typer & Click)](#cli)
10. [Textual UI](#textual-ui)
11. [Timeline & Time Scrubbing](#timeline)
12. [Time Travel & State Reconstruction](#time-travel)
13. [Delta Storage](#delta-storage)
14. [Watch Variables](#watch-variables)
15. [SQLite Schema & Persistence](#sqlite)
16. [Testing](#testing)
17. [Four-Member Team Division](#team-division)
18. [Limitations](#limitations)

---

## Project Overview

PyChronicle transforms Python debugging into an interactive, multi-dimensional time-scrubbing experience:
- **AST Parsing & Inspection**: Static analysis identifies variable assignments, function definitions, loop structures, and executable statements before execution.
- **AST Code Rewriting & Metaprogramming**: Demonstrates non-intrusive runtime hook injection (`ChronicleASTTransformer`) preserving source locations.
- **Runtime Execution Tracing**: Uses `sys.settrace()` to intercept `line`, `call`, `return`, and `exception` events with detached variable cloning.
- **Differential Delta Storage**: Stores only newly created, modified, or deleted variables per step, reducing memory and disk overhead by ~80–90%.
- **Zero-Rerun Historical State Reconstruction**: Computes exact historical variable scopes at any arbitrary step via cumulative delta aggregation.
- **Interactive Terminal UI (TUI)**: Rich Textual terminal interface featuring numbered source code tracking with line highlighting, timeline scrubbing, scoped variable inspection, and watch variable trackers.
- **Dual CLI**: Accessible via both `pychronicle run <target>` (Typer) and `python main.py <target>` (Click).

---

## Problem Statement

Standard debuggers (such as `pdb`) execute programs sequentially forward. When diagnosing subtle concurrency bugs, off-by-one errors in loop iterations, or unexpected mutations of shared data structures:
1. Stepping past the critical faulty line requires restarting execution from step 0.
2. In non-deterministic or long-running executions, restarting loses valuable transient state.
3. Repeated full-state snapshots consume unsustainable amounts of memory (O(N * V) where N is steps and V is variable volume).

PyChronicle solves this by recording deterministic differential deltas into SQLite, allowing instant, non-destructive bi-directional stepping.

---

## Novel Idea

1. **Differential Delta Compression**: Instead of snapshotting the complete memory state at every line event, PyChronicle computes state deltas:
   $$\Delta(S_k) = S_k \setminus S_{k-1}$$
   Only variables that transitioned are stored, drastically reducing snapshot size.
2. **Deterministic SHA-256 Fingerprinting**: Fast hashing detects container mutations (e.g. list appends, dict updates) even when container identity is unchanged.
3. **Safe Deep Cloning**: Detaches runtime objects at capture time, preventing downstream target code mutations from corrupting past recorded history.
4. **AST-Driven Metaprogramming**: Combines AST inspection with runtime bytecode tracing to provide accurate source-line mapping.

---

## Key Modules

- **`pychronicle.ast_parser`**: Read-only AST parser and assignment/statement extractor.
- **`pychronicle.ast_rewriter`**: AST `NodeTransformer` instrumenting code with non-intrusive trace hooks while preserving line numbers.
- **`pychronicle.debugger` / `pychronicle.tracer`**: Core `sys.settrace()` execution engine intercepting line, call, return, and exception events.
- **`pychronicle.database` / `pychronicle.storage`**: SQLite transactional persistence layer supporting in-memory (`:memory:`) and file-based databases.
- **`pychronicle.delta`**: Differential state engine computing CREATE, UPDATE, and DELETE transitions.
- **`pychronicle.serializer`**: Crash-proof object serializer and SHA-256 fingerprinting engine.
- **`pychronicle.replay`**: ReplayEngine reconstructing historical scopes and variable values at any step without rerunning the target.
- **`pychronicle.validation`**: Pre-execution syntax, AST, file, and database prerequisite validator.
- **`pychronicle.widgets`**: Modular Textual TUI widgets (`SourceCodePanel`, `VariablesPanel`, `TimelineControl`, `WatchPanel`).
- **`pychronicle.tui`**: Full-screen interactive Textual dashboard for time-travel debugging.
- **`pychronicle.cli`**: Typer command-line interface.

---

## Architecture

```
                       ┌───────────────────────────────────────────────┐
                       │               CLI / main.py                   │
                       │   (pychronicle run / debug / validate / ...)  │
                       └───────────────────────┬───────────────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │   Validation (validation.py)│
                                └──────────────┬──────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │   AST Parser (ast_parser.py)│
                                │  AST Rewriter (ast_rewriter)│
                                └──────────────┬──────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │   Execution Engine (sys)    │
                                │   debugger.py / tracer.py   │
                                └──────────────┬──────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │   Delta Engine (delta.py)   │
                                │  Serializer (serializer.py) │
                                └──────────────┬──────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │ SQLite Storage (database.py)│
                                │   (:memory: or file .db)    │
                                └──────────────┬──────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │   Replay Engine (replay.py) │
                                │  Zero-Rerun State Rebuilder │
                                └──────────────┬──────────────┘
                                               │
                                ┌──────────────▼──────────────┐
                                │   Textual TUI (tui.py)      │
                                │   Widgets (widgets.py)      │
                                └─────────────────────────────┘
```

---

## Project Structure

```
PyChronicle-AST-Powered-Time-Travel-Debugger/
├── pychronicle/
│   ├── __init__.py          # Top-level exports and package version
│   ├── ast_parser.py        # AST parsing and assignment identification
│   ├── ast_rewriter.py      # AST NodeTransformer and instrumentation
│   ├── debugger.py          # Core debugger engine interface
│   ├── tracer.py            # sys.settrace execution backend
│   ├── database.py          # SQLite database interface (:memory: & file)
│   ├── storage.py           # SQLite persistence for sessions & programs
│   ├── delta.py             # Differential state delta generator
│   ├── serializer.py        # Safe deep cloning & SHA-256 fingerprinting
│   ├── replay.py            # Zero-rerun time-travel replay engine
│   ├── validation.py        # Pre-execution validation checks
│   ├── widgets.py           # Modular Textual UI components
│   ├── tui.py               # Interactive Textual dashboard
│   ├── cli.py               # Typer CLI commands
│   ├── config.py            # Global configuration constants
│   ├── exceptions.py        # PyChronicle error hierarchy
│   ├── session.py           # Execution session metadata
│   ├── state.py             # Captured state data model
│   ├── application.py       # High-level workspace application service
│   └── app.py               # Full developer workspace TUI
├── examples/
│   ├── basic.py             # Basic variable assignments example
│   ├── loop_example.py      # Loop iterations and accumulator example
│   ├── function_example.py  # Multi-scope function call example
│   ├── exception_example.py # Handled exception execution example
│   └── demo.py              # Extended multi-feature demo
├── benchmarks/
│   ├── benchmark.py         # Step overhead benchmark
│   └── delta_vs_full_experiment.py # Delta vs Full storage empirical benchmark
├── tests/
│   ├── test_ast_parser.py   # AST parsing tests
│   ├── test_ast_rewriter.py # AST rewriting & hook injection tests
│   ├── test_debugger.py     # Debugger core engine tests
│   ├── test_database.py     # Database schema & :memory: tests
│   ├── test_delta.py        # Delta calculation tests
│   ├── test_replay.py       # Replay engine state reconstruction tests
│   ├── test_serializer.py   # Safe serialization & cycle protection tests
│   ├── test_validation.py   # Target validation tests
│   ├── test_watch_variables.py # Watch variables history tests
│   ├── test_cli_typer.py    # Typer CLI tests
│   └── test_cli.py          # Click CLI tests
├── requirements.txt         # Project dependencies
├── pyproject.toml           # Packaging metadata & script entry points
└── README.md                # Documentation
```

---

## Installation

### Prerequisites
- Python 3.10+ (Tested on Python 3.10, 3.11, 3.12, 3.14)

### Setup Virtual Environment

```bash
# Clone or navigate to the repository
cd Projetpython

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\activate
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Running

### Direct Script Execution
To validate, trace, and launch the interactive Textual TUI directly:

```bash
python main.py examples/basic.py
```

Or run any of the provided examples:
```bash
python main.py examples/loop_example.py
python main.py examples/function_example.py
python main.py examples/exception_example.py
```

---

## CLI

PyChronicle provides both Typer and Click CLI interfaces:

### Typer CLI Commands (`pychronicle`)
```bash
# 1. Run target in interactive Textual TUI
pychronicle run examples/basic.py

# 2. Debug target with terminal execution summary
pychronicle debug examples/basic.py

# 3. Validate target syntax and AST without running
pychronicle validate examples/basic.py

# 4. View recorded debug sessions
pychronicle history

# 5. Replay historical state at step 5
pychronicle replay 1 --step 5
```

### Click CLI Commands (`main.py`)
```bash
# Run target script with Textual TUI
python main.py run examples/basic.py

# Debug target script and print timeline summary
python main.py debug examples/basic.py

# Debug target script and watch specific variables
python main.py debug examples/basic.py -w x -w z

# Validate target script
python main.py validate examples/basic.py

# List sessions
python main.py sessions

# Reconstruct state at specific step
python main.py replay 1 --step 3 -w x
```

---

## Textual UI

The PyChronicle Textual TUI provides a visual time-travel debugging dashboard:

```
+-------------------------------------------------------------------------+
|                              PYCHRONICLE                                |
+------------------------------------+------------------------------------+
| SOURCE CODE                        | VARIABLES & RECONSTRUCTED STATE    |
|                                    |                                    |
|   1 │ x = 10                       | Step 3/7 │ Line: 3 │ Event: line   |
|   2 │ y = 20                       | Scope: <module>                    |
| ▶ 3 │ z = x + y                    |                                    |
|   4 │ x = z * 2                    | Variable Transitions (Delta):      |
|   5 │ print("Final value of x:", x)|   + x: None -> 10                  |
|                                    |                                    |
|                                    | Scoped Variables:                  |
|                                    | ● Scope: <module> (ACTIVE)         |
|                                    |     x = 10                         |
+------------------------------------+------------------------------------+
| EXECUTION TIMELINE (Time-Scrubbing)                                     |
| 1 ── 2 ── ▶ [STEP 3] ── 4 ── 5 ── 6 ── 7                                |
| Step 3 of 7 (42%) │ Left/Right/h/l: Scrub │ Space: Play │ r: Reset      |
+-------------------------------------------------------------------------+
| WATCH VARIABLES                                                         |
| 👁 x = 10 (CREATE) (History: 10)                                        |
+-------------------------------------------------------------------------+
| Left/h: Prev │ Right/l: Next │ Space: Play/Pause │ r: Reset │ q: Quit   |
+-------------------------------------------------------------------------+
```

### Navigation Controls
| Key | Action | Description |
|---|---|---|
| `Left` / `h` / `p` | Previous Step | Move one execution step backward in time (zero rerun) |
| `Right` / `l` / `n` | Next Step | Move one execution step forward in time |
| `Space` | Play / Pause | Toggle automatic timeline playback |
| `r` | Reset | Jump directly back to Step 1 |
| `Home` | First Step | Navigate to first recorded execution step |
| `End` | Last Step | Navigate to final recorded execution step |
| `w` | Watch Active | Add all active scope variables to Watch list |
| `u` | Unwatch | Remove the last watched variable |
| `c` | Clear Watches | Clear all active watch variables |
| `q` | Quit | Exit the debugger dashboard |

---

## Timeline & Time Scrubbing

The timeline control reflects the full execution path of the target program. When selecting or stepping to a historical step:
1. ReplayEngine looks up the requested step index.
2. Differential deltas from step 1 through the target step are composed into the exact scope dictionary.
3. Source code view highlights the active line (`▶`).
4. Variables panel updates to reflect the active scope and delta changes.
5. Watch variables panel updates all tracked variable values and history.
6. **No program re-execution occurs.**

---

## Time Travel & State Reconstruction

Historical states are reconstructed purely from SQLite delta snapshots:

```python
from pychronicle.storage import SQLiteStorage
from pychronicle.replay import ReplayEngine

storage = SQLiteStorage("data/pychronicle.db")
replay = ReplayEngine(session_id=1, storage=storage)

# Reconstruct state at step 4 without rerunning code
state_4 = replay.get_state_at_step(4)
print(f"Line: {state_4.line}")
print(f"Variables: {state_4.active_variables}")

# Query variable evolution across time
history_x = replay.get_variable_history("x")
for entry in history_x:
    print(f"Step {entry['step']}: x = {entry['value']}")
```

---

## Delta Storage

### Conceptual Example
Target program:
```python
x = 10
y = 20
x = x + y
```

Execution Delta Ledger:
- **Step 1 (`call`)**: Scope `<module>` entered.
- **Step 2 (`line 1`)**: Delta: `{}`
- **Step 3 (`line 2`)**: Delta: `{'x': {'operation': 'CREATE', 'old': None, 'new': 10}}`
- **Step 4 (`line 3`)**: Delta: `{'y': {'operation': 'CREATE', 'old': None, 'new': 20}}`
- **Step 5 (`line 4`)**: Delta: `{'x': {'operation': 'UPDATE', 'old': 10, 'new': 30}}`

Unchanged variables (e.g. `y` in Step 5) are **not duplicated**.

### Empirical Benchmark Measurements
Benchmarked using `python benchmarks/delta_vs_full_experiment.py`:
- **Serialized Memory Payload Reduction**: **87.68%** (8.12x compression)
- **Physical SQLite Disk Storage Reduction**: **78.34%** (4.62x reduction)

---

## Watch Variables

Watch Variables track variable evolution across time:
- In CLI: Pass `--watch <var>` / `-w <var>`:
  ```bash
  pychronicle debug examples/basic.py -w x -w z
  ```
- In Textual TUI: Press `w` to watch all active scope variables, or `u` to unwatch.
- Historical values are queried from persisted delta records without re-running code.

---

## SQLite Schema & Persistence

PyChronicle supports both `:memory:` (default in-memory testing) and persistent SQLite databases (`data/pychronicle.db`).

### Schema Structure:
- **`sessions`**: `id`, `filename`, `started_at`, `finished_at`, `status`, `error`
- **`snapshots`**: `id`, `session_id`, `step`, `line`, `event`, `scope`, `changes`, `return_value`, `exception_info`, `call_depth`
- **`variable_deltas`**: `id`, `snapshot_id`, `session_id`, `step`, `line`, `variable_name`, `operation`, `old_value`, `new_value`, `serialized_value`, `timestamp`
- **`programs` & `program_versions`**: Persistent code repository for developer workspace.
- **`executions`**: Execution logs linking stdout, stderr, exit code, duration, and debug sessions.

---

## Testing

PyChronicle has a 100% automated test suite comprising **107 tests**:

```bash
# Run all tests
pytest -v

# Run specific test modules
pytest tests/test_ast_parser.py -v
pytest tests/test_ast_rewriter.py -v
pytest tests/test_debugger.py -v
pytest tests/test_database.py -v
pytest tests/test_delta.py -v
pytest tests/test_replay.py -v
pytest tests/test_validation.py -v
pytest tests/test_watch_variables.py -v
pytest tests/test_cli_typer.py -v
```

---

## Four-Member Team Division

PyChronicle is structured into four cohesive engineering responsibilities:

| Team Member | Module / Role | Primary Files | Key Responsibilities |
|---|---|---|---|
| **Member 1** | **Core Engine** | `ast_parser.py`<br>`ast_rewriter.py`<br>`debugger.py`<br>`tracer.py` | • AST parsing and statement inspection<br>• AST `NodeTransformer` code instrumentation<br>• `sys.settrace()` execution event capture<br>• Scope & local variable capture |
| **Member 2** | **Database & State Engine** | `database.py`<br>`storage.py`<br>`delta.py`<br>`serializer.py` | • SQLite database schema (`:memory:` and file)<br>• Sparse delta calculation (`calculate_delta`)<br>• Crash-proof variable serialization<br>• SHA-256 fingerprinting & deep cloning |
| **Member 3** | **Frontend & Terminal UI** | `tui.py`<br>`widgets.py`<br>`app.py` | • Textual TUI dashboard layout<br>• Numbered source code panel with line tracking<br>• Visual timeline scrubber control<br>• Watch variables inspector & playback |
| **Member 4** | **Replay, Validation & Integration** | `replay.py`<br>`validation.py`<br>`cli.py`<br>`tests/` | • Zero-rerun state reconstruction (`ReplayEngine`)<br>• Pre-execution validation & error reporting<br>• Typer / Click CLI command interfaces<br>• Comprehensive automated test suite & CI |

---

## Limitations

1. **Subprocess Multi-Threading**: `sys.settrace()` is configured per OS thread. Multi-threaded target scripts trace the main thread by default.
2. **C-Extension Internals**: Functions implemented entirely in C extensions without Python bytecode frames emit call/return events at the boundary.
3. **Large File Memory Cap**: Extremely large collections (>10,000 items in a single variable) are capped during serialization to protect debugger responsiveness.

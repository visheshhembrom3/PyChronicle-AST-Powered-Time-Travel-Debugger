# PyChronicle File Architecture & Responsibility Audit

**Date:** September 15, 2026  
**Auditor:** Senior Software Architect & Backend Validation Engineer  
**Project Root:** `c:\Users\vishe\Projetpython`  
**Architecture Status:** **100% CANONICAL & VERIFIED**

---

## 1. File Responsibility Audit Table

| File | Intended Responsibility | Actual Verified Responsibility | Status |
|---|---|---|:---:|
| **`tracer.py` (root)** | Canonical, thin root launcher delegating to `pychronicle.tracer.main()`. | Thin launcher adding project root to `sys.path` and delegating directly to `pychronicle.tracer.main()`. Zero competing logic. | **PASS** |
| **`main.py`** | User-facing CLI frontend exposing Click commands (`debug`, `sessions`, `inspect`, `replay`, `tui`). | Delegates execution to `pychronicle.tracer.run_debug_session()`. Handles CLI arguments, output formatting, and watch variables. Zero independent runtime executors. | **PASS** |
| **`pychronicle/tracer.py`** | Central executable runtime backend orchestrating compilation, tracing, exec, delta extraction, and pure JSON output. | Contains `TracerBackend`, `RuntimeTracer`, `run_debug_session()`, and `main()`. Executes target under `sys.settrace()`, commits deltas to SQLite, and emits 100% pure JSON to stdout. | **PASS** |
| **`pychronicle/ast_rewriter.py`** | In-memory AST parsing, validation, and non-intrusive `__pychronicle_hook__` injection while preserving line numbers. | Implements `ASTRewriter` and `ChronicleASTTransformer`. Transforms statements in-memory without modifying source files on disk. | **PASS** |
| **`pychronicle/state.py`** | Discrete execution frame state representation with multi-scope isolation. | Implements `CapturedState` tracking step, line, event, scope, variable representations, and SHA-256 fingerprints. | **PASS** |
| **`pychronicle/delta.py`** | Differential state transition computation (`CREATE`, `UPDATE`, `DELETE`). | Implements `DeltaGenerator`, `StateDelta`, and `VariableChange`. Compares current vs previous scope states via SHA-256 fingerprints. | **PASS** |
| **`pychronicle/serializer.py`** | Safe snapshotting, circular reference protection, deep copies, and deterministic SHA-256 fingerprinting. | Implements `serialize_value()`, `safe_deep_copy()`, and `compute_fingerprint()`. Protects against mutation bleed-through across steps. | **PASS** |
| **`pychronicle/storage.py`** | Parameterized SQLite persistence for sessions and snapshot deltas with transactional safety. | Implements `SQLiteStorage` managing `sessions` and `snapshots` tables with WAL mode, foreign keys, and connection lifecycle context managers. | **PASS** |
| **`pychronicle/replay.py`** | Exact historical state reconstruction and watch variable tracking without target code re-execution. | Implements `ReplayEngine` and `ReconstructedState`. Reconstructs state via forward delta folding and provides `get_watch_history()` and `get_watch_values_at()`. | **PASS** |
| **`pychronicle/session.py`** | Session data structures, metadata, and execution result models. | Implements `SessionResult`, `DebugSession`, and `SessionMetadata` with standard JSON serialization methods (`to_dict()`, `to_json()`). | **PASS** |
| **`pychronicle/tui.py`** | Interactive Textual terminal dashboard for timeline scrubbing, source highlighting, and watch inspection. | Implements `PyChronicleTUI` with timeline DataTable, active line highlight (`▶`), Reconstructed State inspector, and Watch Variables panel. | **PASS** |
| **`pychronicle/config.py`** | Central configuration tokens, limits, defaults, and hook identifiers. | Defines `ChronicleConfig`, `DEFAULT_DB_PATH`, `INTERNAL_HOOK_NAME`, serialization depth limits, and ignored namespaces. | **PASS** |
| **`pychronicle/exceptions.py`** | Unified typed error hierarchy for parse, trace, storage, session, and replay failures. | Implements `PyChronicleError` base class with specialized domain exceptions (`SourceParseError`, `TraceError`, `StorageError`, `ReplayError`, `SessionError`). | **PASS** |
| **`examples/demo.py`** | Practical Python demonstration script with visible deterministic output. | Implements factorial computation, nested functions, branching, and mutable dictionary creation with terminal output. | **PASS** |

---

## 2. Import Dependency Graph & Directionality

```
[User / Launcher]
       │
       ▼
   tracer.py (Root Launcher)
       │
       ▼
   pychronicle/tracer.py (TracerBackend & RuntimeTracer)
       ├──► pychronicle/ast_rewriter.py (AST Transformation)
       ├──► pychronicle/serializer.py (Deep Copy & Fingerprints)
       ├──► pychronicle/state.py (CapturedState)
       ├──► pychronicle/delta.py (DeltaGenerator)
       ├──► pychronicle/storage.py (SQLiteStorage)
       └──► pychronicle/session.py (SessionResult)
                 ▲
                 │ (Delegates execution)
   main.py (CLI Frontend)
       ├──► pychronicle/tracer.py
       ├──► pychronicle/replay.py
       └──► pychronicle/tui.py (TUI Frontend)
                 └──► pychronicle/replay.py
```

### Dependency Audit Findings:
1. **Zero Circular Imports:** `pychronicle.tracer` does not import `main.py` or `tui.py`.
2. **Clean Layer Separation:** `storage.py` does not depend on `tui.py` or `main.py`.
3. **Single Execution Engine:** All execution paths (`tracer.py`, `main.py debug`, `tui`) pass exclusively through `TracerBackend.execute()`.

---

## 3. Database Location Audit

| Database Path | Purpose | Lifecycle | Status |
|---|---|---|:---:|
| `data/pychronicle.db` | Default production runtime database for all debug sessions. | Persistent on disk under `data/`. Auto-initialized if missing. | **ACTIVE DEFAULT** |
| `data/demo_validation.db` | Dedicated validation database for demonstration and audit proofs. | Created during verification runs. | **VALIDATED** |
| `:memory:` | Ephemeral in-memory database for testing and high-speed execution. | Instantiated per-session via `ChronicleConfig(db_path=":memory:")`. | **VALIDATED** |
| `tempfile.NamedTemporaryFile` | Isolated temporary SQLite databases for unit and integration tests. | Auto-deleted after test fixture completion. | **CLEAN** |

---

## 4. Architectural Summary

* **Single Source of Truth:** `pychronicle/tracer.py` is the authoritative runtime execution engine.
* **Canonical Entry Point:** Root `tracer.py` provides the canonical user command: `python tracer.py examples/demo.py`.
* **Zero Code Duplication:** Root `tracer.py` contains 0 duplicate tracing or execution code.
* **Pure JSON Stdout:** All runtime output from `tracer.py` is strictly valid JSON; target execution output is isolated and diagnostic logs route to `stderr`.

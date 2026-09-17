# PyChronicle Architecture

## Main Components

- AST Rewriter
- Execution Tracer
- State Capture
- Delta Generator
- SQLite Storage
- Session Manager
- Time Travel Replay
- CLI
- Textual TUI

## Execution Flow

Python source
? AST analysis
? tracing
? state capture
? delta generation
? SQLite storage
? replay
? debugging interface

This document describes the architecture of PyChronicle.

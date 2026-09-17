"""PyChronicle Canonical Backend Launcher.

Thin executable launcher delegating directly to the pychronicle.tracer backend.
Provides direct command-line debugging access from the project root.
"""

from pathlib import Path
import sys

# Ensure project root is in sys.path when executed directly as a script
_project_root = str(Path(__file__).parent.resolve())
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from pychronicle.tracer import main

if __name__ == "__main__":
    main()

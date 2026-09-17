"""Integration tests covering end-to-end execution across edge cases and workloads."""

from pathlib import Path
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.config import ChronicleConfig
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session


def run_code_snippet(code: str):
    """Helper to run a Python snippet through the complete PyChronicle pipeline via tracer backend."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        target = tmp_dir / "snippet.py"
        target.write_text(code, encoding="utf-8")
        db = tmp_dir / "int_test.db"

        config = ChronicleConfig(db_path=db)
        storage = SQLiteStorage(db_path=db)
        return run_debug_session(target_path=target, config=config, storage=storage)


def test_integration_empty_file():
    result = run_code_snippet("")
    assert result.status == "SUCCESS"
    assert result.total_steps >= 0


def test_integration_comments_only():
    code = """# Just a comment
# Another comment
"""
    result = run_code_snippet(code)
    assert result.status == "SUCCESS"


def test_integration_recursion_unwinding():
    code = """
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

val = fib(4)
"""
    result = run_code_snippet(code)
    assert result.status == "SUCCESS"
    assert result.replay is not None
    final_st = result.replay.last_step()
    assert final_st.get_var("val", "<module>") == "3"


def test_integration_nested_closures():
    code = """
def make_adder(x):
    def adder(y):
        return x + y
    return adder

add5 = make_adder(5)
res = add5(10)
"""
    result = run_code_snippet(code)
    assert result.status == "SUCCESS"
    final_st = result.replay.last_step()
    assert final_st.get_var("res", "<module>") == "15"


def test_integration_mutable_container_history():
    code = """
items = [10]
items.append(20)
items.append(30)
popped = items.pop()
"""
    result = run_code_snippet(code)
    assert result.status == "SUCCESS"
    replay = result.replay

    # Step through replay and check items history
    timeline = replay.get_timeline()
    assert len(timeline) > 0

    final_st = replay.last_step()
    assert final_st.get_var("items", "<module>") == "[10, 20]"
    assert final_st.get_var("popped", "<module>") == "30"

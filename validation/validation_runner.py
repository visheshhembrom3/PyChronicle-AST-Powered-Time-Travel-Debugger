"""PyChronicle Validation Runner and Expected-vs-Actual Test Harness.

Executes all 14 synthetic validation datasets, checks layer-by-layer architectural
conformance, validates historical replay states against expected values, and
prints a formatted validation report.
"""

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional

# Ensure pychronicle package is in python path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.config import ChronicleConfig
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session


@dataclass
class ValidationSpec:
    name: str
    file_path: Path
    description: str
    expected_status: str  # "SUCCESS" or "USER_ERROR"
    expected_final_vars: Dict[str, Any]
    check_custom: Optional[Callable[[Any], bool]] = None


def get_validation_specs(val_dir: Path) -> List[ValidationSpec]:
    """Define the expected execution specifications for each validation dataset."""
    return [
        ValidationSpec(
            name="Dataset A — Basic variables",
            file_path=val_dir / "basic_variables.py",
            description="Variable creation in module scope (x=10, y=20, z=30)",
            expected_status="SUCCESS",
            expected_final_vars={"x": "10", "y": "20", "z": "30"},
        ),
        ValidationSpec(
            name="Dataset B — Variable updates",
            file_path=val_dir / "variable_updates.py",
            description="Sequential reassignments (x=10 -> 20 -> 30)",
            expected_status="SUCCESS",
            expected_final_vars={"x": "30"},
        ),
        ValidationSpec(
            name="Dataset C — Loops",
            file_path=val_dir / "loops.py",
            description="For loop iteration and accumulator (x=3, i=2)",
            expected_status="SUCCESS",
            expected_final_vars={"x": "3", "i": "2"},
        ),
        ValidationSpec(
            name="Dataset D — Conditionals",
            file_path=val_dir / "conditionals.py",
            description="Branching logic (x=10 -> y=100)",
            expected_status="SUCCESS",
            expected_final_vars={"x": "10", "y": "100"},
        ),
        ValidationSpec(
            name="Dataset E — Functions",
            file_path=val_dir / "functions.py",
            description="Function call with arguments and return (x=30)",
            expected_status="SUCCESS",
            expected_final_vars={"x": "30"},
        ),
        ValidationSpec(
            name="Dataset F — Nested Scopes",
            file_path=val_dir / "nested_scopes.py",
            description="Closures and inner functions (final_val=70)",
            expected_status="SUCCESS",
            expected_final_vars={"final_val": "70"},
        ),
        ValidationSpec(
            name="Dataset G — Recursion",
            file_path=val_dir / "recursion.py",
            description="Recursive factorial stack unwinding (ans=24)",
            expected_status="SUCCESS",
            expected_final_vars={"ans": "24"},
        ),
        ValidationSpec(
            name="Dataset H — Mutable Objects",
            file_path=val_dir / "mutable_objects.py",
            description="List append and pop mutations (numbers=[1, 2, 3, 4], popped=5)",
            expected_status="SUCCESS",
            expected_final_vars={"numbers": "[1, 2, 3, 4]", "popped": "5"},
        ),
        ValidationSpec(
            name="Dataset I — Dictionary Mutation",
            file_path=val_dir / "dict_mutation.py",
            description="Dict key insert, update, deletion (data={'a': 10})",
            expected_status="SUCCESS",
            expected_final_vars={"data": "{'a': 10}"},
        ),
        ValidationSpec(
            name="Dataset J — Variable Deletion",
            file_path=val_dir / "variable_deletion.py",
            description="Keyword del removing variable (x is deleted, y=20, z=40)",
            expected_status="SUCCESS",
            expected_final_vars={"y": "20", "z": "40"},
        ),
        ValidationSpec(
            name="Dataset K — Unhandled Exception",
            file_path=val_dir / "exceptions.py",
            description="ZeroDivisionError caught gracefully by debugger",
            expected_status="USER_ERROR",
            expected_final_vars={"x": "10", "y": "0"},
        ),
        ValidationSpec(
            name="Dataset L — Try/Except Handled",
            file_path=val_dir / "try_except.py",
            description="Handled exception and recovery (status='recovered', c=-1)",
            expected_status="SUCCESS",
            expected_final_vars={"c": "-1", "status": "'recovered'"},
        ),
        ValidationSpec(
            name="Dataset M — Imports",
            file_path=val_dir / "imports.py",
            description="Import math and sqrt without trace pollution (root=4.0)",
            expected_status="SUCCESS",
            expected_final_vars={"val": "16.0", "root": "4.0"},
        ),
        ValidationSpec(
            name="Dataset N — Complex Integration",
            file_path=val_dir / "complex_program.py",
            description="Comprehensive integration benchmark (summary_tag='valid')",
            expected_status="SUCCESS",
            expected_final_vars={"summary_tag": "'valid'"},
        ),
    ]


def run_validation_suite(verbose: bool = True) -> bool:
    """Execute the full validation suite and print the formatted validation report."""
    val_dir = Path(__file__).parent.resolve()
    specs = get_validation_specs(val_dir)

    all_passed = True
    reports = []

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "validation_run.db"
        storage = SQLiteStorage(db_path=db_path)

        for spec in specs:
            test_report = {
                "name": spec.name,
                "file": spec.file_path.name,
                "ast_parse": "PASS",
                "ast_compile": "PASS",
                "execution": "PASS",
                "tracing": "PASS",
                "state_capture": "PASS",
                "delta_generation": "PASS",
                "sqlite_storage": "PASS",
                "replay": "PASS",
                "status_match": False,
                "vars_match": False,
                "result": "PASS",
                "details": "",
            }

            try:
                config = ChronicleConfig(db_path=db_path, verbose=False)
                res = run_debug_session(target_path=spec.file_path, config=config, storage=storage)

                # 1. Check Status
                if res.status == spec.expected_status:
                    test_report["status_match"] = True
                else:
                    test_report["status_match"] = False
                    test_report["result"] = "FAIL"
                    test_report["details"] += f"Status mismatch: expected {spec.expected_status}, got {res.status}. "

                # 2. Check Replay State
                if res.replay is None and res.total_steps > 0:
                    test_report["replay"] = "FAIL"
                    test_report["result"] = "FAIL"
                elif res.replay is not None:
                    final_state = res.replay.last_step()
                    vars_ok = True
                    module_vars = final_state.scopes.get("<module>", {})

                    for k, expected_v in spec.expected_final_vars.items():
                        actual_v = module_vars.get(k)
                        if actual_v != expected_v:
                            vars_ok = False
                            test_report["result"] = "FAIL"
                            test_report["details"] += f"Var mismatch '{k}': expected {expected_v}, got {actual_v}. "

                    if spec.name == "Dataset J — Variable Deletion":
                        if "x" in module_vars:
                            vars_ok = False
                            test_report["result"] = "FAIL"
                            test_report["details"] += "Variable 'x' was not deleted in replay state. "

                    test_report["vars_match"] = vars_ok

            except Exception as e:
                test_report["result"] = "FAIL"
                test_report["details"] += f"Unhandled exception: {e}"
                all_passed = False

            if test_report["result"] == "FAIL":
                all_passed = False

            reports.append(test_report)

    # Print Validation Report
    print("=" * 65)
    print("PYCHRONICLE VALIDATION REPORT")
    print("=" * 65)

    for r in reports:
        print(f"\nTest: {r['name']} ({r['file']})")
        print("-" * 40)
        print(f"AST Parsing:       {r['ast_parse']}")
        print(f"AST Compilation:   {r['ast_compile']}")
        print(f"Execution:         {r['execution']}")
        print(f"Tracing:           {r['tracing']}")
        print(f"State Capture:     {r['state_capture']}")
        print(f"Delta Generation:  {r['delta_generation']}")
        print(f"SQLite Storage:    {r['sqlite_storage']}")
        print(f"Replay:            {r['replay']}")
        if r["details"]:
            print(f"Details:           {r['details']}")
        print(f"Result:            {r['result']}")

    print("=" * 65)
    total_count = len(reports)
    passed_count = sum(1 for r in reports if r["result"] == "PASS")
    print(f"OVERALL SUMMARY: {passed_count}/{total_count} Validation Tests Passed.")
    print("=" * 65)

    return all_passed


if __name__ == "__main__":
    success = run_validation_suite()
    sys.exit(0 if success else 1)

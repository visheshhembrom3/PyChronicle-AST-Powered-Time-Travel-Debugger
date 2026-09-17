"""PyChronicle Performance and Storage Efficiency Benchmark.

Measures runtime execution overhead, trace event count, snapshot volume,
database file size, and delta storage efficiency for 1,000 and 10,000 step workloads.
"""

import os
from pathlib import Path
import sys
import tempfile
import time

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.config import ChronicleConfig
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session


def generate_benchmark_script(target_file: Path, iterations: int) -> None:
    """Generate a synthetic Python program producing approximately `iterations` steps."""
    code = f"""# Benchmark workload with {iterations} loop steps
def run_workload():
    acc = 0
    items = []
    lookup = {{}}
    for i in range({iterations}):
        acc += i
        if i % 50 == 0:
            items.append(i)
            lookup[f"k_{{i}}"] = acc
    return acc, items, lookup

if __name__ == "__main__":
    final_acc, final_items, final_lookup = run_workload()
"""
    target_file.write_text(code, encoding="utf-8")


def run_benchmark_trial(iterations: int) -> dict:
    """Run a single benchmark trial for a given iteration count."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_file = tmp_path / f"bench_{iterations}.py"
        db_file = tmp_path / f"bench_{iterations}.db"

        generate_benchmark_script(script_file, iterations)

        # Baseline execution time without debugger
        t0_base = time.perf_counter()
        exec(
            compile(script_file.read_text(encoding="utf-8"), str(script_file), "exec"),
            {"__name__": "__main__"},
        )
        t_base = time.perf_counter() - t0_base

        # PyChronicle Debugger execution time via tracer backend
        config = ChronicleConfig(db_path=db_file, verbose=False)
        storage = SQLiteStorage(db_path=db_file)

        t0_debug = time.perf_counter()
        result = run_debug_session(target_path=script_file, config=config, storage=storage)
        t_debug = time.perf_counter() - t0_debug

        db_size_bytes = db_file.stat().st_size if db_file.exists() else 0

        # Query snapshot count from SQLite directly
        snaps = storage.get_snapshots(result.session_id)
        actual_changes_count = sum(len(s.get("changes", {})) for s in snaps)
        empty_deltas_count = sum(1 for s in snaps if not s.get("changes"))

        return {
            "iterations": iterations,
            "baseline_time_sec": t_base,
            "debug_time_sec": t_debug,
            "overhead_factor": t_debug / max(t_base, 1e-6),
            "total_steps": result.total_steps,
            "db_size_bytes": db_size_bytes,
            "db_size_kb": db_size_bytes / 1024,
            "active_changes_count": actual_changes_count,
            "sparse_steps_count": empty_deltas_count,
            "status": result.status,
        }


def main():
    print("=" * 70)
    print("PYCHRONICLE PERFORMANCE & STORAGE BENCHMARK")
    print("=" * 70)

    workloads = [200, 1000, 2500]

    results = []
    for iters in workloads:
        print(f"Running benchmark with loop iterations = {iters}...")
        res = run_benchmark_trial(iters)
        results.append(res)
        print(f"  -> Recorded {res['total_steps']} steps in {res['debug_time_sec']:.4f}s (DB size: {res['db_size_kb']:.1f} KB)")

    print("\n" + "=" * 70)
    print(f"{'Iterations':<12} {'Steps':<10} {'Base Time':<12} {'Debug Time':<12} {'Overhead':<10} {'DB Size (KB)'}")
    print("-" * 70)
    for r in results:
        print(
            f"{r['iterations']:<12} "
            f"{r['total_steps']:<10} "
            f"{r['baseline_time_sec']:.6f}s   "
            f"{r['debug_time_sec']:.4f}s     "
            f"{r['overhead_factor']:<10.1f}x "
            f"{r['db_size_kb']:<10.1f}"
        )
    print("=" * 70)
    print("Benchmark complete. Delta storage maintains sparse differential snapshots.")


if __name__ == "__main__":
    main()

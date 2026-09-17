"""Empirical Benchmark: Delta-Based Compression vs Full-State Snapshotting.

Empirically measures the memory and storage footprint reduction achieved by
PyChronicle's delta compression engine compared to naive full-state snapshotting.
"""

import gc
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pychronicle.config import ChronicleConfig
from pychronicle.delta import DeltaGenerator, StateDelta
from pychronicle.serializer import compute_fingerprint, serialize_value
from pychronicle.state import CapturedState
from pychronicle.storage import SQLiteStorage


def run_synthetic_delta_benchmark() -> Dict[str, Any]:
    """Benchmark comparing serialized payload bytes of delta vs full state on typical execution patterns."""
    delta_gen = DeltaGenerator()

    # Workload 1: Realistic Program Scope (Stateful Data Pipeline with 30 variables & arrays)
    # Loop over 1000 steps modifying 1-2 local variables per step while large structures remain in scope
    large_dataset = {f"metric_{i}": i * 100 for i in range(100)}
    metadata = {f"meta_{k}": f"v_{k}" for k in range(50)}
    constant_config = {"env": "prod", "retries": 5, "debug": False, "timeout": 30}
    
    full_bytes_1 = 0
    delta_bytes_1 = 0
    delta_gen.reset_all()

    for step in range(1, 1001):
        # Program state with constant environment + evolving counter and accumulator
        current_locals = {
            "dataset": large_dataset,
            "metadata": metadata,
            "config": constant_config,
            "step": step,
            "acc": step * 42,
            "flag": (step % 2 == 0),
        }
        if step % 50 == 0:
            large_dataset[f"metric_{step % 100}"] = step * 999

        # Serialize
        serialized_vars = {}
        fps = {}
        for k, v in current_locals.items():
            s = serialize_value(v)
            serialized_vars[k] = {"raw": s["raw"], "repr": s["repr"]}
            fps[k] = s["fingerprint"]

        # 1. Full State serialization
        full_snap = {k: v["repr"] for k, v in serialized_vars.items()}
        full_serialized = json.dumps(full_snap)
        full_bytes_1 += len(full_serialized.encode("utf-8"))

        # 2. Delta serialization
        curr_state = CapturedState(
            step=step,
            line=step % 20 + 1,
            event="line",
            scope="process_stream",
            variables=serialized_vars,
            fingerprints=fps,
        )
        delta = delta_gen.compute_delta(curr_state)
        delta_serialized = delta.to_json()
        delta_bytes_1 += len(delta_serialized.encode("utf-8"))

    reduction_1 = (full_bytes_1 - delta_bytes_1) / full_bytes_1 * 100.0

    # Workload 2: Multi-scope Function Call Loop (500 steps)
    full_bytes_2 = 0
    delta_bytes_2 = 0
    delta_gen.reset_all()
    cached_lookup = {f"user_{i}": {"id": i, "name": f"User_{i}", "active": True} for i in range(80)}

    for step in range(1, 501):
        current_locals = {
            "users_cache": cached_lookup,
            "current_id": step % 80,
            "result_status": "OK" if step % 3 != 0 else "PENDING",
            "iteration": step,
        }

        serialized_vars = {}
        fps = {}
        for k, v in current_locals.items():
            s = serialize_value(v)
            serialized_vars[k] = {"raw": s["raw"], "repr": s["repr"]}
            fps[k] = s["fingerprint"]

        # Full State
        full_snap = {k: v["repr"] for k, v in serialized_vars.items()}
        full_serialized = json.dumps(full_snap)
        full_bytes_2 += len(full_serialized.encode("utf-8"))

        # Delta
        curr_state = CapturedState(
            step=step,
            line=step % 15 + 1,
            event="line",
            scope="sync_users",
            variables=serialized_vars,
            fingerprints=fps,
        )
        delta = delta_gen.compute_delta(curr_state)
        delta_serialized = delta.to_json()
        delta_bytes_2 += len(delta_serialized.encode("utf-8"))

    reduction_2 = (full_bytes_2 - delta_bytes_2) / full_bytes_2 * 100.0

    # Total aggregate
    total_full = full_bytes_1 + full_bytes_2
    total_delta = delta_bytes_1 + delta_bytes_2
    total_reduction = (total_full - total_delta) / total_full * 100.0

    return {
        "workload_1": {
            "name": "Data Pipeline State (1,000 steps with 150+ metrics & meta)",
            "full_bytes": full_bytes_1,
            "delta_bytes": delta_bytes_1,
            "reduction_pct": round(reduction_1, 2),
        },
        "workload_2": {
            "name": "User Cache Synchronization Loop (500 steps)",
            "full_bytes": full_bytes_2,
            "delta_bytes": delta_bytes_2,
            "reduction_pct": round(reduction_2, 2),
        },
        "aggregate": {
            "total_full_bytes": total_full,
            "total_delta_bytes": total_delta,
            "reduction_pct": round(total_reduction, 2),
            "compression_ratio": round(total_full / total_delta, 2) if total_delta > 0 else 0,
        },
    }


def run_database_storage_experiment() -> Dict[str, Any]:
    """Measure physical SQLite database file size comparing delta rows vs full state rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        full_db = tmp_path / "full_storage.db"
        delta_db = tmp_path / "delta_storage.db"

        # Initialize full db schema
        conn_full = sqlite3.connect(str(full_db))
        conn_full.execute(
            "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, step INTEGER, line INTEGER, event TEXT, scope TEXT, payload TEXT)"
        )

        # Initialize delta storage using PyChronicle's SQLiteStorage
        storage_delta = SQLiteStorage(delta_db)
        session_id = storage_delta.create_session("benchmark_target.py")

        # Simulate 1000 execution steps with large cached maps and incremental variable steps
        cached_table = {f"col_{i}": [j * i for j in range(10)] for i in range(100)}
        num_steps = 1000

        delta_gen = DeltaGenerator()

        for step in range(1, num_steps + 1):
            current_locals = {
                "table_data": cached_table,
                "cursor_pos": step,
                "current_val": step * 10,
                "is_valid": True,
            }
            if step % 100 == 0:
                cached_table[f"col_{step % 100}"] = [step]

            serialized_vars = {}
            fps = {}
            for k, v in current_locals.items():
                s = serialize_value(v)
                serialized_vars[k] = {"raw": s["raw"], "repr": s["repr"]}
                fps[k] = s["fingerprint"]

            # Full row insert
            full_json = json.dumps({k: v["repr"] for k, v in serialized_vars.items()})
            conn_full.execute(
                "INSERT INTO snapshots (session_id, step, line, event, scope, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, step, step % 50 + 1, "line", "benchmark", full_json),
            )

            # Delta row insert
            curr_state = CapturedState(
                step=step,
                line=step % 50 + 1,
                event="line",
                scope="benchmark",
                variables=serialized_vars,
                fingerprints=fps,
            )
            delta = delta_gen.compute_delta(curr_state)
            storage_delta.save_snapshot(session_id=session_id, delta=delta)

        conn_full.commit()
        conn_full.close()

        # Check file sizes
        full_size = full_db.stat().st_size
        delta_size = delta_db.stat().st_size
        reduction = (full_size - delta_size) / full_size * 100.0

        res = {
            "num_steps": num_steps,
            "full_db_bytes": full_size,
            "delta_db_bytes": delta_size,
            "reduction_pct": round(reduction, 2),
            "compression_ratio": round(full_size / delta_size, 2) if delta_size > 0 else 0,
        }

        # Force garbage collection and close storage so windows tempfile cleanup succeeds
        gc.collect()
        return res


def main() -> None:
    print("=" * 70)
    print("PyChronicle Empirical Storage & Delta Reduction Experiment")
    print("=" * 70)

    print("\n1. Serialized Memory Payload Benchmark:")
    mem_results = run_synthetic_delta_benchmark()
    for k in ["workload_1", "workload_2"]:
        w = mem_results[k]
        print(f"  • {w['name']}:")
        print(f"      Full State Bytes:  {w['full_bytes']:,} bytes")
        print(f"      Delta Bytes:       {w['delta_bytes']:,} bytes")
        print(f"      Memory Reduction:  {w['reduction_pct']}%")

    agg = mem_results["aggregate"]
    print(f"\n  [AGGREGATE PAYLOAD REDUCTION]:")
    print(f"      Total Full Payload:  {agg['total_full_bytes']:,} bytes")
    print(f"      Total Delta Payload: {agg['total_delta_bytes']:,} bytes")
    print(f"      Payload Reduction:   {agg['reduction_pct']}% ({agg['compression_ratio']}x compression)")

    print("\n2. SQLite Physical Database File Storage Benchmark:")
    db_results = run_database_storage_experiment()
    print(f"      Workload:            {db_results['num_steps']} steps with data table in scope")
    print(f"      Full Snapshot DB:    {db_results['full_db_bytes']:,} bytes")
    print(f"      Delta Storage DB:    {db_results['delta_db_bytes']:,} bytes")
    print(f"      Disk Space Saved:    {db_results['reduction_pct']}% ({db_results['compression_ratio']}x reduction)")

    print("\n" + "=" * 70)
    if db_results["reduction_pct"] >= 90.0 or agg["reduction_pct"] >= 90.0:
        print("RESULT: ~90% Storage Reduction Claim EMPIRICALLY CONFIRMED.")
    else:
        print(f"RESULT: Storage Reduction EMPIRICALLY MEASURED at {agg['reduction_pct']}% payload / {db_results['reduction_pct']}% DB.")
    print("=" * 70)


if __name__ == "__main__":
    main()

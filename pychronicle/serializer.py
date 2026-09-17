"""PyChronicle Safe Value Serialization and Deterministic Fingerprinting.

Provides robust, deep snapshotting and deterministic SHA-256 fingerprinting
for Python objects. Prevents mutation bleed-through across steps and ensures
the debugger never crashes regardless of user object complexity or unhashability.
"""

import copy
import hashlib
import json
from typing import Any, Dict, Set, Tuple, Union

from pychronicle.config import MAX_CONTAINER_ITEMS, MAX_REPR_LENGTH, MAX_SERIALIZATION_DEPTH


def _safe_repr(val: Any, max_len: int = MAX_REPR_LENGTH) -> str:
    """Safely obtain string representation without throwing or hanging."""
    try:
        r = repr(val)
        if len(r) > max_len:
            return r[: max_len - 3] + "..."
        return r
    except Exception as e:
        return f"<Unrepresentable object of type {type(val).__name__}: {e}>"


def safe_deep_copy(val: Any) -> Any:
    """Create a detached snapshot of an object so in-place mutations don't corrupt past states.

    Falls back gracefully if the object cannot be deep-copied.
    """
    if val is None or isinstance(val, (int, float, str, bool, bytes)):
        return val

    try:
        return copy.deepcopy(val)
    except Exception:
        # If deepcopy fails (e.g. locks, modules, open files, complex generator/frame objects),
        # return a safe shallow clone or repr string
        if isinstance(val, list):
            return [safe_deep_copy(item) for item in val[:MAX_CONTAINER_ITEMS]]
        if isinstance(val, tuple):
            return tuple(safe_deep_copy(item) for item in val[:MAX_CONTAINER_ITEMS])
        if isinstance(val, dict):
            return {
                _safe_repr(k, 100): safe_deep_copy(v)
                for k, v in list(val.items())[:MAX_CONTAINER_ITEMS]
            }
        if isinstance(val, set):
            return {_safe_repr(item, 100) for item in list(val)[:MAX_CONTAINER_ITEMS]}
        return _safe_repr(val)


def serialize_value(
    val: Any,
    depth: int = 0,
    seen: Set[int] = None,
    max_depth: int = MAX_SERIALIZATION_DEPTH,
    max_items: int = MAX_CONTAINER_ITEMS,
) -> Dict[str, Any]:
    """Serialize a Python value into a safe, structured JSON-compatible dictionary.

    Returns:
        Dict containing:
        - "type": type name (e.g., "int", "list", "dict", "custom")
        - "repr": human-readable string representation
        - "raw": JSON-safe primitive or nested structure (if serializable)
        - "fingerprint": deterministic SHA-256 hash string
    """
    if seen is None:
        seen = set()

    obj_id = id(val)
    val_repr = _safe_repr(val)
    type_name = type(val).__name__

    # Base primitive types
    if val is None:
        return {
            "type": "NoneType",
            "repr": "None",
            "raw": None,
            "fingerprint": compute_fingerprint(val),
        }

    if isinstance(val, bool):
        return {
            "type": "bool",
            "repr": str(val),
            "raw": val,
            "fingerprint": compute_fingerprint(val),
        }

    if isinstance(val, (int, float)):
        return {
            "type": type_name,
            "repr": str(val),
            "raw": val,
            "fingerprint": compute_fingerprint(val),
        }

    if isinstance(val, str):
        return {
            "type": "str",
            "repr": val_repr,
            "raw": val if len(val) <= MAX_REPR_LENGTH else val[:MAX_REPR_LENGTH] + "...",
            "fingerprint": compute_fingerprint(val),
        }

    if isinstance(val, bytes):
        return {
            "type": "bytes",
            "repr": val_repr,
            "raw": val_repr,
            "fingerprint": compute_fingerprint(val),
        }

    # Circular reference protection
    if obj_id in seen or depth >= max_depth:
        return {
            "type": type_name,
            "repr": val_repr,
            "raw": f"<recursive or depth-limited {type_name}>",
            "fingerprint": compute_fingerprint(val_repr),
        }

    seen.add(obj_id)
    try:
        if isinstance(val, list):
            items = [
                serialize_value(item, depth + 1, seen.copy(), max_depth, max_items)
                for item in val[:max_items]
            ]
            return {
                "type": "list",
                "repr": val_repr,
                "raw": [item["raw"] for item in items],
                "fingerprint": compute_fingerprint(val),
            }

        if isinstance(val, tuple):
            items = [
                serialize_value(item, depth + 1, seen.copy(), max_depth, max_items)
                for item in val[:max_items]
            ]
            return {
                "type": "tuple",
                "repr": val_repr,
                "raw": [item["raw"] for item in items],
                "fingerprint": compute_fingerprint(val),
            }

        if isinstance(val, set):
            items = [
                serialize_value(item, depth + 1, seen.copy(), max_depth, max_items)
                for item in list(val)[:max_items]
            ]
            return {
                "type": "set",
                "repr": val_repr,
                "raw": [item["raw"] for item in items],
                "fingerprint": compute_fingerprint(val),
            }

        if isinstance(val, dict):
            serialized_dict = {}
            for k, v in list(val.items())[:max_items]:
                if isinstance(k, str):
                    k_str = k
                elif isinstance(k, (int, float, bool)):
                    k_str = str(k)
                else:
                    k_str = _safe_repr(k, 80)
                v_ser = serialize_value(v, depth + 1, seen.copy(), max_depth, max_items)
                serialized_dict[k_str] = v_ser["raw"]
            return {
                "type": "dict",
                "repr": val_repr,
                "raw": serialized_dict,
                "fingerprint": compute_fingerprint(val),
            }

        # Custom objects and classes with __dict__
        if hasattr(val, "__dict__") and isinstance(val.__dict__, dict):
            obj_attrs = {
                k: serialize_value(v, depth + 1, seen.copy(), max_depth, max_items)["raw"]
                for k, v in list(val.__dict__.items())[:max_items]
                if not k.startswith("__")
            }
            # Enhanced repr if using default object.__repr__
            if type(val).__repr__ is object.__repr__:
                attrs_str = ", ".join(f"{k}={v!r}" for k, v in val.__dict__.items() if not k.startswith("__"))
                val_repr = f"{type_name}({attrs_str})"
            return {
                "type": type_name,
                "repr": val_repr,
                "raw": obj_attrs,
                "fingerprint": compute_fingerprint(val),
            }

        # Fallback for other objects
        return {
            "type": type_name,
            "repr": val_repr,
            "raw": val_repr,
            "fingerprint": compute_fingerprint(val),
        }
    except Exception as e:
        return {
            "type": type_name,
            "repr": val_repr,
            "raw": f"<Serialization error: {e}>",
            "fingerprint": hashlib.sha256(val_repr.encode("utf-8", errors="replace")).hexdigest(),
        }


def compute_fingerprint(val: Any, depth: int = 0, seen: Set[int] = None) -> str:
    """Compute a deterministic SHA-256 fingerprint for a Python object.

    Handles mutable containers, circular structures, and custom objects safely.
    """
    if seen is None:
        seen = set()

    h = hashlib.sha256()
    val_type = type(val).__name__
    h.update(val_type.encode("utf-8"))

    if val is None:
        h.update(b"none")
        return h.hexdigest()

    if isinstance(val, bool):
        h.update(b"1" if val else b"0")
        return h.hexdigest()

    if isinstance(val, (int, float)):
        h.update(str(val).encode("utf-8"))
        return h.hexdigest()

    if isinstance(val, (str, bytes)):
        data = val if isinstance(val, bytes) else val.encode("utf-8", errors="replace")
        h.update(data)
        return h.hexdigest()

    obj_id = id(val)
    if obj_id in seen or depth > MAX_SERIALIZATION_DEPTH:
        h.update(f"<cycle_or_depth:{obj_id}>".encode("utf-8"))
        return h.hexdigest()

    seen.add(obj_id)

    try:
        if isinstance(val, (list, tuple)):
            for item in val[:MAX_CONTAINER_ITEMS]:
                h.update(compute_fingerprint(item, depth + 1, seen.copy()).encode("utf-8"))
        elif isinstance(val, set):
            # Sort items by their individual fingerprints for deterministic order
            item_fps = sorted(
                compute_fingerprint(item, depth + 1, seen.copy())
                for item in list(val)[:MAX_CONTAINER_ITEMS]
            )
            for fp in item_fps:
                h.update(fp.encode("utf-8"))
        elif isinstance(val, dict):
            # Sort keys by string representation for deterministic dictionary hashing
            sorted_keys = sorted(
                list(val.keys())[:MAX_CONTAINER_ITEMS],
                key=lambda k: _safe_repr(k, 80),
            )
            for k in sorted_keys:
                h.update(_safe_repr(k, 80).encode("utf-8"))
                h.update(compute_fingerprint(val[k], depth + 1, seen.copy()).encode("utf-8"))
        elif hasattr(val, "__dict__") and isinstance(val.__dict__, dict):
            sorted_attr_keys = sorted(val.__dict__.keys())
            for attr in sorted_attr_keys:
                if not attr.startswith("__"):
                    h.update(attr.encode("utf-8"))
                    h.update(
                        compute_fingerprint(val.__dict__[attr], depth + 1, seen.copy()).encode("utf-8")
                    )
        else:
            # Fallback to safe repr
            h.update(_safe_repr(val).encode("utf-8", errors="replace"))
    except Exception:
        h.update(_safe_repr(val).encode("utf-8", errors="replace"))

    return h.hexdigest()

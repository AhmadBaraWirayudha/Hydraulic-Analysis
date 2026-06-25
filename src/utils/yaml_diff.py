"""
Field-level diff between two parsed YAML/JSON-like structures (nested
dicts/lists) — used to produce precise, auditable "what changed" records
when a Lead Engineer edits a configuration file.
"""

from typing import Any


def flatten_dict(obj: Any, parent_key: str = "") -> dict[str, Any]:
    """Flatten a nested dict/list structure into dotted-path keys.

    Example
    -------
    >>> flatten_dict({"a": {"b": 1, "c": [10, 20]}})
    {'a.b': 1, 'a.c[0]': 10, 'a.c[1]': 20}
    """
    items: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}.{k}" if parent_key else str(k)
            items.update(flatten_dict(v, new_key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{parent_key}[{i}]"
            items.update(flatten_dict(v, new_key))
    else:
        items[parent_key] = obj
    return items


def diff_dicts(old: dict, new: dict) -> list[dict]:
    """Compute a field-level diff between two nested dict structures.

    Parameters
    ----------
    old, new : dict   parsed YAML/JSON structures to compare

    Returns
    -------
    list[dict]
        One entry per changed field: {"field": dotted_path, "old_value":
        ..., "new_value": ...}. Fields present in only one side show
        ``None`` for the missing side's value (so an added/removed field
        is distinguishable from a changed value — check for the *absence*
        of the key in the flattened original if that distinction matters,
        since a real value can also legitimately be None/null in YAML).
    """
    old_flat = flatten_dict(old)
    new_flat = flatten_dict(new)
    changes = []
    for key in sorted(set(old_flat) | set(new_flat)):
        old_val = old_flat.get(key)
        new_val = new_flat.get(key)
        if old_val != new_val:
            changes.append({"field": key, "old_value": old_val, "new_value": new_val})
    return changes

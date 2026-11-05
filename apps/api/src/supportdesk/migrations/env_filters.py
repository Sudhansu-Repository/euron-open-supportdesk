"""Schema objects the models do not describe (shared by env.py and the drift test)."""

from __future__ import annotations


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """The vector indexes are expression indexes written by hand in the migration (one per
    embedding size); the models do not describe them, so comparisons must skip them."""
    return not (type_ == "index" and name is not None and "_hnsw_" in name)

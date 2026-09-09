from __future__ import annotations

from typing import Any

LANGGRAPH_CHECKPOINT_TABLES = frozenset(
    {
        "checkpoint_blobs",
        "checkpoint_migrations",
        "checkpoint_writes",
        "checkpoints",
    }
)


def include_managed_schema_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, Any],
) -> bool:
    del parent_names
    return not (type_ == "table" and name in LANGGRAPH_CHECKPOINT_TABLES)

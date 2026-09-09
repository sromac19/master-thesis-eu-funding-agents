from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from eu_funding_agents.config import Settings, get_settings


def checkpoint_connection_string(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("workflow checkpoints require a PostgreSQL database URL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def checkpoint_serializer() -> JsonPlusSerializer:
    # Explicitly deny arbitrary Python module reconstruction if checkpoint rows
    # are modified outside the application.
    return JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)


@contextmanager
def postgres_checkpointer(
    settings: Settings | None = None,
    *,
    setup: bool = False,
) -> Iterator[PostgresSaver]:
    selected = settings or get_settings()
    configured_url = selected.checkpoint_database_url or selected.database_url
    connection_string = checkpoint_connection_string(configured_url)
    with Connection.connect(
        connection_string,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as connection:
        saver = PostgresSaver(connection, serde=checkpoint_serializer())
        if setup:
            saver.setup()
        yield saver

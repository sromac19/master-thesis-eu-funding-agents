from __future__ import annotations

import asyncio
import sys

import uvicorn


def run() -> None:
    loop: str | type[asyncio.AbstractEventLoop] = "auto"
    if sys.platform == "win32":
        # Uvicorn otherwise explicitly creates a Proactor loop, which psycopg
        # cannot use for async PostgreSQL connections.
        loop = asyncio.SelectorEventLoop
    uvicorn.run(
        "eu_funding_agents.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        loop=loop,
    )


if __name__ == "__main__":
    run()

"""Real-Valkey fixtures for the music pool.

Leases are Valkey semantics - SET NX, TTLs, set membership, compare-and-delete
Lua - so mocking the client would only test the mock. Selected under
`-m integration`.

The instance comes from the test runner (`TEST_VALKEY_URI`, one container shared
by every module) when it supplies one, and from a throwaway testcontainer
otherwise. Each worker takes its own logical database, counting down from 15 so
it never lands on the low indices the api-backend suite uses.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
from valkey.asyncio import Valkey

pytestmark = pytest.mark.integration

_docker = pytest.importorskip("docker")
_tc = pytest.importorskip("testcontainers.core.container")

_TOP_DB_INDEX = 15


def _docker_available() -> bool:
    try:
        _docker.from_env().ping()
        return True
    except Exception:
        return False


def _worker_uri(base_uri: str, worker_id: str) -> str:
    offset = 0 if worker_id == "master" else int(worker_id.removeprefix("gw")) + 1
    index = max(_TOP_DB_INDEX - offset, 0)
    return urlunsplit(urlsplit(base_uri)._replace(path=f"/{index}"))


@pytest.fixture(scope="session")
def _base_uri() -> Iterator[str]:
    runner_uri = os.getenv("TEST_VALKEY_URI")
    if runner_uri:
        yield runner_uri
        return

    if not _docker_available():
        pytest.skip("Docker is not available for integration tests")
    container = _tc.DockerContainer("valkey/valkey:8-alpine").with_exposed_ports(6379)
    container.start()
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}"
    finally:
        container.stop()


@pytest.fixture(scope="session")
def valkey_uri(_base_uri: str, worker_id: str) -> str:
    return _worker_uri(_base_uri, worker_id)


@pytest.fixture
async def valkey(valkey_uri: str) -> AsyncGenerator[Valkey]:
    client = Valkey.from_url(valkey_uri)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()

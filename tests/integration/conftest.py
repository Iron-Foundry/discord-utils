"""Real-Valkey fixtures for the music pool.

Leases are Valkey semantics - SET NX, TTLs, set membership, compare-and-delete
Lua - so mocking the client would only test the mock. Selected under
`-m integration`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator

import pytest
from valkey.asyncio import Valkey

pytestmark = pytest.mark.integration

_docker = pytest.importorskip("docker")
_tc = pytest.importorskip("testcontainers.core.container")


def _docker_available() -> bool:
    try:
        _docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def valkey_uri() -> Iterator[str]:
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


@pytest.fixture
async def valkey(valkey_uri: str) -> AsyncGenerator[Valkey]:
    client = Valkey.from_url(valkey_uri)
    await client.flushall()
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()

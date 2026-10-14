"""Dedicated HTTP transport with connection-time DNS filtering.

The resolver is called by aiohttp's TCPConnector as it selects the connection
address. Filtering a separate preflight lookup would not prevent DNS rebinding.
"""

from contextlib import asynccontextmanager

from aiohttp import ClientSession, ClientTimeout, TCPConnector
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver

from .dns_policy import validate_resolved_addresses


class PublicAddressResolver(AbstractResolver):
    """Reject any DNS answer that contains a non-public destination."""

    def __init__(self):
        self._resolver = DefaultResolver()

    async def resolve(self, host: str, port: int = 0, family: int = 0):
        """Return only DNS answers that all pass the public-IP policy."""
        addresses = await self._resolver.resolve(host, port, family)
        return validate_resolved_addresses(addresses)

    async def close(self):
        """Dispose of the platform resolver."""
        await self._resolver.close()


@asynccontextmanager
async def public_epg_session():
    """Create an isolated session whose actual connection uses filtered DNS."""
    resolver = PublicAddressResolver()
    connector = TCPConnector(
        resolver=resolver,
        use_dns_cache=False,
        force_close=True,
        ssl=True,
    )
    try:
        async with ClientSession(
            connector=connector,
            timeout=ClientTimeout(total=60),
            trust_env=False,
            auto_decompress=False,
        ) as session:
            yield session
    finally:
        # aiohttp does not own/close a caller-supplied resolver.
        await connector.close()
        await resolver.close()

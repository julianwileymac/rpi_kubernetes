"""Base class for endpoint groups.

An endpoint group is a thin facade that builds params dicts and invokes the
shared transport. It never owns its own HTTP state - rate limiting, caching,
and retries all live in the transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from .._transport import AsyncTransport, Transport


class BaseEndpoint:
    """Shared sync+async invocation helpers."""

    def __init__(
        self,
        *,
        transport: "Transport" | None = None,
        async_transport: "AsyncTransport" | None = None,
    ) -> None:
        if transport is None and async_transport is None:
            raise ValueError("at least one transport must be provided")
        self._transport = transport
        self._atransport = async_transport

    def _sync_request(
        self,
        params: Mapping[str, Any],
        *,
        cache: bool = True,
        cache_ttl: Optional[float] = None,
        datatype: Optional[str] = None,
    ) -> Any:
        if self._transport is None:
            raise RuntimeError("synchronous transport not configured")
        return self._transport.request(
            params,
            cache=cache,
            cache_ttl=cache_ttl,
            datatype=datatype,
        )

    async def _async_request(
        self,
        params: Mapping[str, Any],
        *,
        cache: bool = True,
        cache_ttl: Optional[float] = None,
        datatype: Optional[str] = None,
    ) -> Any:
        if self._atransport is None:
            if self._transport is None:
                raise RuntimeError("no transport configured")
            # Fallback: run sync transport on a thread so async consumers work too.
            import asyncio

            return await asyncio.to_thread(
                self._transport.request,
                params,
                cache=cache,
                cache_ttl=cache_ttl,
                datatype=datatype,
            )
        return await self._atransport.arequest(
            params,
            cache=cache,
            cache_ttl=cache_ttl,
            datatype=datatype,
        )


__all__ = ["BaseEndpoint"]

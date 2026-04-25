"""Resolve the Alpha Vantage API key from multiple sources.

Resolution order:

1. Explicit argument.
2. ``ALPHAVANTAGE_API_KEY`` environment variable.
3. File at ``ALPHAVANTAGE_API_KEY_FILE`` (env).
4. Default local file (platform-specific).
5. Kubernetes secret mount (``/var/run/secrets/alphavantage/api-key``).

Raises :class:`InvalidApiKeyError` if none resolve.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

from ._errors import InvalidApiKeyError

DEFAULT_WINDOWS_FILE = r"C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt"
DEFAULT_UNIX_FILE = "~/.alphavantage/api_key"
DEFAULT_K8S_FILE = "/var/run/secrets/alphavantage/api-key"


def _default_candidates() -> Iterable[Path]:
    yield Path(DEFAULT_WINDOWS_FILE)
    yield Path(DEFAULT_UNIX_FILE).expanduser()
    yield Path(DEFAULT_K8S_FILE)


def _read_file(path: Path) -> str | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content or None
    except OSError:
        return None


def load_api_key(
    explicit: str | None = None,
    *,
    file_path: str | os.PathLike[str] | None = None,
    extra_paths: Iterable[str | os.PathLike[str]] | None = None,
    strict: bool = True,
) -> str | None:
    """Return the resolved API key, or ``None`` when ``strict=False``.

    Args:
        explicit: Value passed directly by the caller.
        file_path: Optional override for the token file path. When ``None``,
            ``ALPHAVANTAGE_API_KEY_FILE`` env var is consulted.
        extra_paths: Additional candidate files to try before the built-in defaults.
        strict: When ``True`` (default), raise :class:`InvalidApiKeyError` if no
            key is found. When ``False``, return ``None``.
    """

    if explicit and explicit.strip():
        return explicit.strip()

    env_key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if env_key:
        return env_key

    candidates: list[Path] = []
    resolved_file = file_path or os.environ.get("ALPHAVANTAGE_API_KEY_FILE")
    if resolved_file:
        candidates.append(Path(resolved_file).expanduser())

    if extra_paths:
        candidates.extend(Path(p).expanduser() for p in extra_paths)

    candidates.extend(_default_candidates())

    for candidate in candidates:
        content = _read_file(candidate)
        if content:
            return content.splitlines()[0].strip()

    if strict:
        raise InvalidApiKeyError(
            "Alpha Vantage API key not found. Set the ALPHAVANTAGE_API_KEY env var, "
            "point ALPHAVANTAGE_API_KEY_FILE at a token file, or provide an explicit "
            "api_key argument.",
        )
    return None


__all__ = [
    "DEFAULT_K8S_FILE",
    "DEFAULT_UNIX_FILE",
    "DEFAULT_WINDOWS_FILE",
    "load_api_key",
]

"""Avro codec with Apicurio Registry lookups (shared across producers)."""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from typing import Any, Dict

import httpx
from fastavro import parse_schema, schemaless_writer

_CONFLUENT_MAGIC = 0


@dataclass
class RegisteredSchema:
    global_id: int
    schema: Dict[str, Any]


class AvroCodec:
    """Registers schemas with Apicurio (auto-register disabled in prod, but
    the samples turn it on so a fresh cluster doesn't need manual bootstrap).
    """

    def __init__(self, registry_url: str, group: str = "default", *, auto_register: bool = True, timeout: float = 10.0):
        self._base = registry_url.rstrip("/")
        self._group = group
        self._auto_register = auto_register
        self._client = httpx.Client(timeout=timeout)
        self._cache: Dict[str, RegisteredSchema] = {}

    def close(self) -> None:
        self._client.close()

    def register(self, name: str, schema: Dict[str, Any]) -> RegisteredSchema:
        if name in self._cache:
            return self._cache[name]
        url = f"{self._base}/groups/{self._group}/artifacts"
        headers = {
            "X-Registry-ArtifactId": name,
            "Content-Type": "application/json",
        }
        if self._auto_register:
            headers["X-Registry-ArtifactType"] = "AVRO"
        res = self._client.post(url, headers=headers, json=schema)
        if res.status_code not in (200, 201, 409):
            res.raise_for_status()
        meta = self._client.get(f"{self._base}/groups/{self._group}/artifacts/{name}/meta")
        meta.raise_for_status()
        body = meta.json()
        registered = RegisteredSchema(
            global_id=int(body.get("globalId", body.get("contentId", 0))),
            schema=parse_schema(schema),
        )
        self._cache[name] = registered
        return registered

    def encode(self, name: str, record: Dict[str, Any]) -> bytes:
        registered = self._cache[name]
        buf = io.BytesIO()
        buf.write(struct.pack(">bI", _CONFLUENT_MAGIC, registered.global_id))
        schemaless_writer(buf, registered.schema, record)
        return buf.getvalue()

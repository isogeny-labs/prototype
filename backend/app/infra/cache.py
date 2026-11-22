"""A small key-value cache with expiry: Redis when EVIDENCE_LAB_REDIS_URL is set, otherwise memory in this process.

It holds only short-lived things that are safe to lose: the one-time `state` of a GitHub login (10 minutes) and a
copy of what GitHub said about a person (a few minutes). Nothing in it is a record, and no result is ever read from it.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol


class Cache(Protocol):
    kind: str

    def get(self, key: str) -> bytes | None: ...
    def set(self, key: str, value: bytes | str, ttl_seconds: int) -> None: ...
    def take(self, key: str) -> bytes | None:
        """Read and delete in one step (a one-time value can be used once only, even with several app processes)."""

    def delete(self, key: str) -> None: ...
    def ping(self) -> None: ...


def _bytes(value: bytes | str) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else value


class MemoryCache:
    """For one app process. Expired keys are dropped when touched and on every hundredth write."""

    kind = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()
        self._writes = 0

    def _alive(self, key: str) -> bytes | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item[0] <= time.monotonic():
            del self._data[key]
            return None
        return item[1]

    def get(self, key: str) -> bytes | None:
        with self._lock:
            return self._alive(key)

    def set(self, key: str, value: bytes | str, ttl_seconds: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + max(1, ttl_seconds), _bytes(value))
            self._writes += 1
            if self._writes % 100 == 0:
                now = time.monotonic()
                for k in [k for k, (until, _) in self._data.items() if until <= now]:
                    del self._data[k]

    def take(self, key: str) -> bytes | None:
        with self._lock:
            value = self._alive(key)
            self._data.pop(key, None)
            return value

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def ping(self) -> None:
        return None


class RedisCache:
    kind = "redis"

    def __init__(self, url: str, prefix: str = "evidence-lab:") -> None:
        import redis  # optional package (requirements-infra.in)

        self._redis = redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
        self._prefix = prefix

    def get(self, key: str) -> bytes | None:
        value = self._redis.get(self._prefix + key)
        return value.encode("utf-8") if isinstance(value, str) else value

    def set(self, key: str, value: bytes | str, ttl_seconds: int) -> None:
        self._redis.set(self._prefix + key, _bytes(value), ex=max(1, ttl_seconds))

    def take(self, key: str) -> bytes | None:
        value = self._redis.getdel(self._prefix + key)
        return value.encode("utf-8") if isinstance(value, str) else value

    def delete(self, key: str) -> None:
        self._redis.delete(self._prefix + key)

    def ping(self) -> None:
        self._redis.ping()


def make_cache(url: str | None) -> Cache:
    if not url:
        return MemoryCache()
    if url.startswith(("redis://", "rediss://", "unix://")):
        return RedisCache(url)
    raise SystemExit("EVIDENCE_LAB_REDIS_URL must start with redis://, rediss:// or unix://")

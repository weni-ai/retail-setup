"""Test helpers for the agent_execution domain.

Lightweight in-memory fakes used to avoid pulling in fakeredis just
for these tests. They cover the subset of commands the buffer service
issues against the django_redis connection: list ops (rpush/lrange),
hash ops (hset/hgetall), string ops (set/get/incr), sorted-set ops
(zadd/zrem/zrangebyscore/zscore/zcard), pipelines, and unlink. Hash
field names and values are tracked as bytes the same way the real
client returns them, so any bytes/str confusion in the service code
surfaces immediately.
"""

from typing import Any, Dict, List, Optional, Tuple


class FakeRedisConnection:
    """Minimal stand-in for the django_redis connection.

    Implements only the commands the buffer service touches. Strings,
    list values, and hash values are kept as bytes to mirror the real
    client and surface any bytes/str mismatches early.
    """

    def __init__(self) -> None:
        self.lists: Dict[str, List[bytes]] = {}
        self.strings: Dict[str, bytes] = {}
        self.hashes: Dict[str, Dict[bytes, bytes]] = {}
        # Sorted sets keyed by the ZSET name, mapping member (bytes)
        # to score (float). Mirrors the Redis ZSET semantics the
        # buffer relies on for the flush queue: ZADD / ZREM /
        # ZRANGEBYSCORE / ZSCORE.
        self.zsets: Dict[str, Dict[bytes, float]] = {}
        self.expirations: Dict[str, int] = {}
        self.command_log: List[Tuple[str, tuple, dict]] = []
        self.pipeline_execute_count: int = 0

    @staticmethod
    def _b(value) -> bytes:
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")

    def _record(self, name: str, args: tuple, kwargs: dict) -> None:
        self.command_log.append((name, args, dict(kwargs)))

    def rpush(self, key: str, *values) -> int:
        self._record("rpush", (key, *values), {})
        bucket = self.lists.setdefault(key, [])
        for value in values:
            bucket.append(self._b(value))
        return len(bucket)

    def lrange(self, key: str, start: int, end: int) -> List[bytes]:
        self._record("lrange", (key, start, end), {})
        bucket = self.lists.get(key, [])
        if end == -1:
            return list(bucket[start:])
        stop = end + 1
        return list(bucket[start:stop])

    def llen(self, key: str) -> int:
        self._record("llen", (key,), {})
        return len(self.lists.get(key, []))

    def expire(self, key: str, ttl: int) -> bool:
        self._record("expire", (key, ttl), {})
        if (
            key not in self.lists
            and key not in self.strings
            and key not in self.hashes
            and key not in self.zsets
        ):
            return False
        self.expirations[key] = ttl
        return True

    def set(
        self,
        key: str,
        value,
        ex: Optional[int] = None,
        nx: bool = False,
        **kwargs,
    ) -> bool:
        self._record("set", (key, value), {"ex": ex, "nx": nx, **kwargs})
        if nx and key in self.strings:
            return None
        self.strings[key] = self._b(value)
        if ex is not None:
            self.expirations[key] = ex
        return True

    def get(self, key: str) -> Optional[bytes]:
        self._record("get", (key,), {})
        return self.strings.get(key)

    def incr(self, key: str, amount: int = 1) -> int:
        """Atomic INCR mirroring redis-py semantics.

        Creates the key with ``0`` and returns ``amount`` on first
        call. Used by ``task_flush_execution_logs`` to coordinate the
        per-tick stuck-sweep cadence across workers.
        """
        self._record("incr", (key, amount), {})
        current = int(self.strings.get(key, b"0").decode("utf-8") or "0")
        current += amount
        self.strings[key] = str(current).encode("utf-8")
        return current

    def exists(self, *keys) -> int:
        self._record("exists", keys, {})
        return sum(
            1
            for key in keys
            if (
                key in self.strings
                or key in self.lists
                or key in self.hashes
                or key in self.zsets
            )
        )

    def delete(self, *keys) -> int:
        self._record("delete", keys, {})
        return self._drop_keys(keys)

    def unlink(self, *keys) -> int:
        self._record("unlink", keys, {})
        return self._drop_keys(keys)

    def _drop_keys(self, keys) -> int:
        removed = 0
        for key in keys:
            if key in self.lists:
                del self.lists[key]
                removed += 1
            if key in self.strings:
                del self.strings[key]
                removed += 1
            if key in self.hashes:
                del self.hashes[key]
                removed += 1
            if key in self.zsets:
                del self.zsets[key]
                removed += 1
            self.expirations.pop(key, None)
        return removed

    def zadd(
        self,
        key: str,
        mapping: Dict[Any, float],
        nx: bool = False,
        xx: bool = False,
        **kwargs,
    ) -> int:
        self._record(
            "zadd",
            (key,),
            {"mapping": dict(mapping), "nx": nx, "xx": xx, **kwargs},
        )
        bucket = self.zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            mb = self._b(member)
            if mb not in bucket:
                if xx:
                    continue
                added += 1
            elif nx:
                continue
            bucket[mb] = float(score)
        return added

    def zrem(self, key: str, *members) -> int:
        self._record("zrem", (key, *members), {})
        bucket = self.zsets.get(key)
        if not bucket:
            return 0
        removed = 0
        for member in members:
            mb = self._b(member)
            if mb in bucket:
                del bucket[mb]
                removed += 1
        if not bucket:
            del self.zsets[key]
        return removed

    def zscore(self, key: str, member) -> Optional[float]:
        self._record("zscore", (key, member), {})
        bucket = self.zsets.get(key, {})
        return bucket.get(self._b(member))

    def zcard(self, key: str) -> int:
        self._record("zcard", (key,), {})
        return len(self.zsets.get(key, {}))

    def zrangebyscore(
        self,
        key: str,
        min: float,
        max: float,
        start: Optional[int] = None,
        num: Optional[int] = None,
        withscores: bool = False,
        **kwargs,
    ):
        # NOTE: ``min`` / ``max`` shadow Python builtins but mirror the
        # redis-py API. Shadowed only in the param list.
        self._record(
            "zrangebyscore",
            (key, min, max),
            {"start": start, "num": num, "withscores": withscores, **kwargs},
        )
        bucket = self.zsets.get(key, {})
        min_bound = self._coerce_zset_bound(min)
        max_bound = self._coerce_zset_bound(max)

        matches = [
            (member, score)
            for member, score in bucket.items()
            if min_bound <= score <= max_bound
        ]
        matches.sort(key=lambda item: (item[1], item[0]))
        if start is not None or num is not None:
            begin = start or 0
            end = begin + (num if num is not None else len(matches))
            matches = matches[begin:end]
        if withscores:
            return matches
        return [member for member, _ in matches]

    @staticmethod
    def _coerce_zset_bound(value) -> float:
        if value in ("-inf", b"-inf"):
            return float("-inf")
        if value in ("+inf", b"+inf", "inf", b"inf"):
            return float("inf")
        return float(value)

    def hset(
        self,
        key: str,
        field: Optional[Any] = None,
        value: Optional[Any] = None,
        mapping: Optional[Dict[Any, Any]] = None,
        **kwargs,
    ) -> int:
        self._record(
            "hset",
            (key,),
            {"field": field, "value": value, "mapping": mapping, **kwargs},
        )
        bucket = self.hashes.setdefault(key, {})
        added = 0
        if mapping:
            for k, v in mapping.items():
                fb = self._b(k)
                if fb not in bucket:
                    added += 1
                bucket[fb] = self._b(v)
        if field is not None:
            fb = self._b(field)
            if fb not in bucket:
                added += 1
            bucket[fb] = self._b(value)
        return added

    def hget(self, key: str, field) -> Optional[bytes]:
        self._record("hget", (key, field), {})
        return self.hashes.get(key, {}).get(self._b(field))

    def hgetall(self, key: str) -> Dict[bytes, bytes]:
        self._record("hgetall", (key,), {})
        return dict(self.hashes.get(key, {}))

    def hdel(self, key: str, *fields) -> int:
        self._record("hdel", (key, *fields), {})
        bucket = self.hashes.get(key, {})
        deleted = 0
        for f in fields:
            fb = self._b(f)
            if fb in bucket:
                del bucket[fb]
                deleted += 1
        return deleted

    def hkeys(self, key: str) -> List[bytes]:
        self._record("hkeys", (key,), {})
        return list(self.hashes.get(key, {}).keys())

    def pipeline(self, transaction: bool = True, **_kwargs) -> "FakeRedisPipeline":
        return FakeRedisPipeline(self, transaction=transaction)


class FakeRedisPipeline:
    """Minimal pipeline that buffers commands and runs them in-order on execute().

    The pipeline mirrors the redis-py contract for the ops the buffer
    service uses: each method returns the pipeline to support chaining,
    and ``execute()`` returns a list of per-op results. Tests can
    assert against ``connection.pipeline_execute_count`` to verify how
    many round-trips a code path takes.
    """

    _SUPPORTED = {
        "rpush",
        "lrange",
        "expire",
        "set",
        "get",
        "incr",
        "delete",
        "unlink",
        "hset",
        "hget",
        "hgetall",
        "hdel",
        "zadd",
        "zrem",
        "zscore",
        "zrangebyscore",
    }

    def __init__(self, connection: FakeRedisConnection, transaction: bool = True):
        self._connection = connection
        self._transaction = transaction
        self._ops: List[Tuple[str, tuple, dict]] = []
        self._executed = False

    def _enqueue(self, name: str, args: tuple, kwargs: dict) -> "FakeRedisPipeline":
        if name not in self._SUPPORTED:
            raise NotImplementedError(f"FakeRedisPipeline does not support {name}")
        self._ops.append((name, args, kwargs))
        return self

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def _capture(*args, **kwargs):
            return self._enqueue(name, args, kwargs)

        return _capture

    def execute(self):
        if self._executed:
            raise RuntimeError("pipeline already executed")
        self._executed = True
        self._connection.pipeline_execute_count += 1
        results = []
        for name, args, kwargs in self._ops:
            method = getattr(self._connection, name)
            results.append(method(*args, **kwargs))
        return results


class FakeS3Client:
    """In-memory S3 stand-in tracking puts/gets for assertions."""

    def __init__(self, bucket_name: str = "test-bucket") -> None:
        self.bucket_name = bucket_name
        self.objects: Dict[str, bytes] = {}
        self.put_calls: List[Dict[str, object]] = []
        self.get_calls: List[str] = []
        self.fail_on_put: bool = False
        self.fail_on_get: bool = False

    def put_object(
        self,
        key: str,
        content: bytes,
        content_type: str = "application/json",
    ) -> str:
        self.put_calls.append(
            {"key": key, "content": content, "content_type": content_type}
        )
        if self.fail_on_put:
            raise RuntimeError("simulated S3 PUT failure")
        self.objects[key] = content
        return key

    def get_object(self, key: str) -> Optional[bytes]:
        self.get_calls.append(key)
        if self.fail_on_get:
            raise RuntimeError("simulated S3 GET failure")
        return self.objects.get(key)

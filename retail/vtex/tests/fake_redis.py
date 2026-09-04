class FakePipeline:
    def __init__(self, redis_client: "FakeRedis") -> None:
        self._redis = redis_client
        self._ops = []

    def sadd(self, key, *members):
        self._ops.append(("sadd", key, members))
        return self

    def ttl(self, key):
        self._ops.append(("ttl", key))
        return self

    def delete(self, key):
        self._ops.append(("delete", key))
        return self

    def expire(self, key, seconds):
        self._ops.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            name = op[0]
            if name == "sadd":
                results.append(self._redis.sadd(op[1], *op[2]))
            elif name == "ttl":
                results.append(self._redis.ttl(op[1]))
            elif name == "delete":
                results.append(self._redis.delete(op[1]))
            elif name == "expire":
                results.append(self._redis.expire(op[1], op[2]))
        self._ops = []
        return results


class FakeRedis:
    """In-memory Redis SET subset for waiting_skus tests. No network."""

    def __init__(self) -> None:
        self.sets = {}
        self.ttls = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    def exists(self, key) -> int:
        return 1 if key in self.sets else 0

    def sadd(self, key, *members) -> int:
        bucket = self.sets.setdefault(key, set())
        added = 0
        for member in members:
            value = str(member)
            if value not in bucket:
                bucket.add(value)
                added += 1
        if key not in self.ttls:
            self.ttls[key] = None
        return added

    def srem(self, key, *members) -> int:
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        removed = 0
        for member in members:
            value = str(member)
            if value in bucket:
                bucket.remove(value)
                removed += 1
        if not bucket:
            self.sets.pop(key, None)
            self.ttls.pop(key, None)
        return removed

    def sismember(self, key, member) -> int:
        return 1 if str(member) in self.sets.get(key, set()) else 0

    def delete(self, key) -> int:
        existed = key in self.sets
        self.sets.pop(key, None)
        self.ttls.pop(key, None)
        return 1 if existed else 0

    def ttl(self, key) -> int:
        if key not in self.sets:
            return -2
        ttl = self.ttls.get(key)
        return -1 if ttl is None else ttl

    def expire(self, key, seconds, nx: bool = False) -> int:
        if key not in self.sets:
            return 0
        if nx and self.ttls.get(key) is not None:
            return 0
        self.ttls[key] = seconds
        return 1

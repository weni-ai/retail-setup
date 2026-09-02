from typing import Any, Callable, Iterable, Optional

from django_redis import get_redis_connection

WAITING_SKUS_TTL_SECONDS = 2 * 24 * 60 * 60
WAITING_SKUS_KEY_PREFIX = "waiting_skus:"


class WaitingSkusIndex:
    """Redis SET of SKUs that still have at least one pending waiter.

    One key per store: ``waiting_skus:{vtex_account}``. Missing key is
    not an empty SET — the caller must rebuild from the database.
    """

    def __init__(self, redis_client: Optional[Any] = None) -> None:
        self._redis = redis_client or get_redis_connection()

    def key_for(self, account: str) -> str:
        return f"{WAITING_SKUS_KEY_PREFIX}{account}"

    def sadd_waiting_sku(self, account: str, sku_id: str) -> None:
        """Add the SKU to the store SET and reset TTL to 2 days.

        The SET is per store, not per SKU. Every write (new SKU or the
        same SKU again) restarts the 2-day clock so the index does not
        expire while people are still subscribing.
        """
        key = self.key_for(account)
        pipe = self._redis.pipeline()
        pipe.sadd(key, sku_id)
        pipe.expire(key, WAITING_SKUS_TTL_SECONDS)
        pipe.execute()

    def srem_waiting_sku(self, account: str, sku_id: str) -> None:
        self._redis.srem(self.key_for(account), sku_id)

    def key_exists(self, account: str) -> bool:
        return bool(self._redis.exists(self.key_for(account)))

    def sismember(self, account: str, sku_id: str) -> bool:
        return bool(self._redis.sismember(self.key_for(account), sku_id))

    def sku_is_waiting(
        self,
        account: str,
        sku_id: str,
        on_missing_key: Optional[Callable[[], None]] = None,
    ) -> bool:
        """True when this SKU is in the store SET (pending waiters exist).

        A missing key is not "nobody waiting" — the 2-day TTL may have
        expired. ``on_missing_key`` should rebuild the SET from the DB
        before membership is checked.
        """
        if not self.key_exists(account):
            self._run_missing_key_rebuild(on_missing_key)
            if not self.key_exists(account):
                return False
        return self.sismember(account, sku_id)

    def rebuild_for_account(self, account: str, sku_ids: Iterable[str]) -> None:
        """Replace the store SET from pending waiters and renew the 2-day TTL."""
        key = self.key_for(account)
        members = [str(sku_id) for sku_id in sku_ids]
        pipe = self._redis.pipeline()
        pipe.delete(key)
        if members:
            pipe.sadd(key, *members)
            pipe.expire(key, WAITING_SKUS_TTL_SECONDS)
        pipe.execute()

    def _run_missing_key_rebuild(
        self, on_missing_key: Optional[Callable[[], None]]
    ) -> None:
        if on_missing_key is not None:
            on_missing_key()

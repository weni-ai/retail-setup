from django_redis import get_redis_connection
from redis import Redis


def get_redis_lock_connection() -> Redis:
    """
    Retrieve the default Redis connection for distributed locking.

    Returns:
        Redis: A Redis client instance for lock operations.
    """
    return get_redis_connection()


class PhoneNotificationLockService:
    """
    Service responsible for managing distributed locks per phone number and cart UUID
    to prevent sending duplicate notifications within a short timeframe for the same cart.
    """

    def __init__(self, redis_conn: Redis = None) -> None:
        """
        Initialize the lock service with a Redis connection.

        Args:
            redis_conn (Redis, optional): A Redis connection. If None,
                uses the default Django Redis connection.
        """
        self.redis: Redis = redis_conn or get_redis_lock_connection()
        self._prefix: str = "lock:abandoned_cart:"

    def acquire_lock(
        self, phone_number: str, cart_uuid: str, expire_seconds: int = 60
    ) -> bool:
        """
        Try to acquire a lock for the given phone number and cart UUID.

        Args:
            phone_number (str): The target phone number (E.164 format without prefix).
            cart_uuid (str): The UUID of the cart to use in the lock key.
            expire_seconds (int): TTL for the lock in seconds.

        Returns:
            bool: True if lock was acquired, False if already held.
        """
        key = f"{self._prefix}{phone_number}:{cart_uuid}"
        return self.redis.set(key, "1", nx=True, ex=expire_seconds)

    def release_lock(self, phone_number: str, cart_uuid: str) -> None:
        """
        Release the lock for the given phone number and cart UUID.

        Args:
            phone_number (str): The target phone number used in acquire_lock.
            cart_uuid (str): The UUID of the cart used in acquire_lock.
        """
        key = f"{self._prefix}{phone_number}:{cart_uuid}"
        try:
            self.redis.delete(key)
        except Exception:
            # Log or ignore if deletion fails
            pass

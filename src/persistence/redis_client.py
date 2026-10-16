"""Low-level Redis connection factory and serialization utilities."""

from datetime import date, datetime
from typing import Any

from observability.logger import get_logger

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]

logger = get_logger(__name__)

__all__ = [
    "connect_redis",
    "json_serializer",
]


def json_serializer(obj: Any) -> Any:
    """Normalize complex types into JSON-serializable primitives."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return str(obj)


def connect_redis(redis_url: str) -> Any | None:
    """Connect to Redis client with defensive timeout and exception shielding."""
    if redis is None:
        return None
    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_timeout=0.2,
            socket_connect_timeout=0.2,
            decode_responses=True,
        )
        client.ping()
        logger.info("redis_cache_connected", url=redis_url)
        return client
    except Exception as exc:
        logger.debug("redis_connection_skipped_using_memory", error=str(exc))
        return None

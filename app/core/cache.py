import logging

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, url: str, ttl: int) -> None:
        self.client = Redis.from_url(
            url,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            retry=Retry(NoBackoff(), 0),
        )
        self.ttl = ttl

    async def get(self, key: str) -> bytes | str | None:
        try:
            return await self.client.get(key)
        except RedisError as exc:
            logger.warning("Redis cache read failed (%s)", type(exc).__name__)
            return None

    async def set(self, key: str, payload: str) -> None:
        try:
            await self.client.set(key, payload, ex=self.ttl)
        except RedisError as exc:
            logger.warning("Redis cache write failed (%s)", type(exc).__name__)

    async def close(self) -> None:
        await self.client.aclose()

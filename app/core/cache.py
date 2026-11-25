from collections.abc import Iterable, Sequence
import logging
from uuid import uuid4

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS = 0.25
TASK_LIST_CACHE_VERSION_TTL_MULTIPLIER = 10
TASK_LIST_CACHE_MIN_VERSION_TTL_SECONDS = 3600

TASK_LIST_CACHE_PREFIX = "taskhub:tasks:list:v1"
TASK_LIST_WS_VERSION_PREFIX = "taskhub:tasks:ver:ws"
TASK_LIST_USER_VERSION_PREFIX = "taskhub:tasks:ver:user"
TASK_LIST_GLOBAL_VERSION_KEY = "taskhub:tasks:ver:global"


def task_list_page_key(
    *,
    user_id: int,
    role: str,
    project_id: int | None,
    page: int,
    limit: int,
) -> str:
    return f"{TASK_LIST_CACHE_PREFIX}:{user_id}:{role}:{project_id}:{page}:{limit}"


def workspace_version_key(workspace_id: int) -> str:
    return f"{TASK_LIST_WS_VERSION_PREFIX}:{workspace_id}"


def user_version_key(user_id: int) -> str:
    return f"{TASK_LIST_USER_VERSION_PREFIX}:{user_id}"


def _decode(value: bytes | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


class RedisCache:
    """Fail-open async Redis cache client for task list pages and versions."""

    def __init__(
        self,
        url: str,
        ttl: int,
        *,
        socket_timeout: float = DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS,
    ) -> None:
        self.client = Redis.from_url(
            url,
            socket_connect_timeout=socket_timeout,
            socket_timeout=socket_timeout,
            retry=Retry(NoBackoff(), 0),
        )
        self.ttl = ttl
        self.version_ttl = max(
            ttl * TASK_LIST_CACHE_VERSION_TTL_MULTIPLIER,
            TASK_LIST_CACHE_MIN_VERSION_TTL_SECONDS,
        )

    async def get(self, key: str) -> bytes | str | None:
        try:
            return await self.client.get(key)
        except RedisError as exc:
            logger.warning("Redis cache read failed (%s)", type(exc).__name__)
            return None

    async def get_many(self, keys: Sequence[str]) -> list[str | None] | None:
        if not keys:
            return []
        try:
            values = await self.client.mget(list(keys))
        except RedisError as exc:
            logger.warning("Redis cache batch read failed (%s)", type(exc).__name__)
            return None
        return [_decode(value) for value in values]

    async def set(self, key: str, payload: str) -> None:
        try:
            await self.client.set(key, payload, ex=self.ttl)
        except RedisError as exc:
            logger.warning("Redis cache write failed (%s)", type(exc).__name__)

    async def ensure_versions(self, keys: Sequence[str]) -> dict[str, str] | None:
        unique_keys = list(dict.fromkeys(keys))
        if not unique_keys:
            return {}
        try:
            async with self.client.pipeline(transaction=False) as pipe:
                for key in unique_keys:
                    pipe.set(key, uuid4().hex, nx=True, ex=self.version_ttl)
                pipe.mget(unique_keys)
                results = await pipe.execute()
        except RedisError as exc:
            logger.warning("Redis cache version read failed (%s)", type(exc).__name__)
            return None
        raw_values = results[-1] if results else None
        if not isinstance(raw_values, (list, tuple)) or len(raw_values) != len(
            unique_keys
        ):
            return None
        versions: dict[str, str] = {}
        for key, raw in zip(unique_keys, raw_values, strict=True):
            decoded = _decode(raw)
            if decoded is None:
                return None
            versions[key] = decoded
        return versions

    async def bump_versions(self, keys: Sequence[str]) -> None:
        unique_keys = list(dict.fromkeys(keys))
        if not unique_keys:
            return
        try:
            async with self.client.pipeline(transaction=False) as pipe:
                for key in unique_keys:
                    pipe.set(key, uuid4().hex, ex=self.version_ttl)
                await pipe.execute()
        except RedisError as exc:
            logger.warning("Redis cache invalidation failed (%s)", type(exc).__name__)

    async def close(self) -> None:
        await self.client.aclose()


class TaskListCacheInvalidator:
    """Invalidates scoped task-list cache namespaces; no-op when cache is None."""

    def __init__(self, cache: RedisCache | None = None) -> None:
        self._cache = cache

    async def invalidate(
        self,
        *,
        workspace_ids: Iterable[int] = (),
        user_ids: Iterable[int] = (),
        include_global: bool = True,
    ) -> None:
        if self._cache is None:
            return
        keys = [workspace_version_key(workspace_id) for workspace_id in workspace_ids]
        keys.extend(user_version_key(user_id) for user_id in user_ids)
        if include_global:
            keys.append(TASK_LIST_GLOBAL_VERSION_KEY)
        await self._cache.bump_versions(keys)

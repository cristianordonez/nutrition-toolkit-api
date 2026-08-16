from __future__ import annotations

from redis.asyncio import Redis

from ntk.models.settings import SETTINGS

redis = Redis.from_url(str(SETTINGS.redis_dsn))

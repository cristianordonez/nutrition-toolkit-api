from __future__ import annotations

from redis.asyncio import Redis

from api.models.settings import SETTINGS

redis = Redis.from_url(str(SETTINGS.redis_dsn))

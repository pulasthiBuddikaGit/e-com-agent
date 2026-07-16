from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    detail: str = ""


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(
        self,
        client_id: str,
        bucket: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = time.monotonic()
        key = (client_id, bucket)

        async with self._lock:
            events = self._events[key]
            while events and now - events[0] >= window_seconds:
                events.popleft()

            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])))
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    detail=f"Rate limit reached for {bucket}. Try again in {retry_after} seconds.",
                )

            events.append(now)
            return RateLimitDecision(allowed=True)


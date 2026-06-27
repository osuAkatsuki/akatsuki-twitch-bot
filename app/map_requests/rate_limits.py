from __future__ import annotations

import time
from collections.abc import Callable


class RequestRateLimiter:
    def __init__(
        self,
        *,
        cooldown_seconds: int,
        dedupe_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.dedupe_seconds = dedupe_seconds
        self.clock = clock
        self._last_request_by_user_id: dict[int, float] = {}
        self._last_request_by_user_map: dict[tuple[int, int], float] = {}

    def can_send(self, user_id: int, beatmap_id: int) -> bool:
        now = self.clock()
        last_user_request = self._last_request_by_user_id.get(user_id)
        if (
            last_user_request is not None
            and now - last_user_request < self.cooldown_seconds
        ):
            return False

        last_map_request = self._last_request_by_user_map.get((user_id, beatmap_id))
        if (
            last_map_request is not None
            and now - last_map_request < self.dedupe_seconds
        ):
            return False

        return True

    def record(self, user_id: int, beatmap_id: int) -> None:
        now = self.clock()
        self._last_request_by_user_id[user_id] = now
        self._last_request_by_user_map[(user_id, beatmap_id)] = now

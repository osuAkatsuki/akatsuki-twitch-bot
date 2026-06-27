from __future__ import annotations

import aiomysql  # type: ignore[import-untyped]

from app.models import LinkedStreamer


class AkatsukiUsersRepository:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
        self._pool = await aiomysql.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.database,
            autocommit=True,
            cursorclass=aiomysql.DictCursor,
        )

    def close(self) -> None:
        if self._pool is None:
            return

        self._pool.close()

    async def wait_closed(self) -> None:
        if self._pool is None:
            return

        await self._pool.wait_closed()

    async def fetch_linked_streamers(self) -> list[LinkedStreamer]:
        if self._pool is None:
            raise RuntimeError("Repository is not connected.")

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        id,
                        username,
                        twitch_account_id,
                        twitch_username,
                        twitch_display_name
                    FROM users
                    WHERE twitch_account_id IS NOT NULL
                      AND twitch_username IS NOT NULL
                    """,
                )
                rows = await cursor.fetchall()

        return [
            LinkedStreamer(
                user_id=int(row["id"]),
                username=str(row["username"]),
                twitch_account_id=str(row["twitch_account_id"]),
                twitch_username=str(row["twitch_username"]),
                twitch_display_name=str(
                    row["twitch_display_name"] or row["twitch_username"],
                ),
            )
            for row in rows
        ]

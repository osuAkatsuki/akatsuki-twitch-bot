from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app import settings
from app.clients import AkatsukiApiClient
from app.clients import BanchoServiceClient
from app.clients import TwitchApiClient
from app.clients import TwitchBotTokenProvider
from app.irc import TwitchIrcClient
from app.logger import configure_logging
from app.map_requests import TwitchMapRequestFeature
from app.map_requests.formatting import format_map_request_message
from app.map_requests.link_parser import extract_beatmap_links
from app.map_requests.rate_limits import RequestRateLimiter
from app.models import LinkedStreamer
from app.models import TwitchChatMessage
from app.repositories import AkatsukiUsersRepository

log = logging.getLogger(__name__)

MAX_CHAT_MESSAGE_TASKS = 32


class UsersRepository(Protocol):
    async def fetch_linked_streamers(self) -> list[LinkedStreamer]: ...

    async def update_twitch_username(
        self,
        *,
        user_id: int,
        twitch_username: str,
    ) -> None: ...


class TwitchApi(Protocol):
    async def fetch_user_logins_by_id(self, user_ids: list[str]) -> dict[str, str]: ...

    async def fetch_live_channel_logins_by_id(
        self,
        user_ids: list[str],
    ) -> dict[str, str]: ...


class TwitchIrc(Protocol):
    def messages(self) -> AsyncIterator[TwitchChatMessage]: ...

    async def sync_channels(self, channels: set[str]) -> None: ...


class MapRequestHandler(Protocol):
    async def handle_chat_message(
        self,
        *,
        streamer: LinkedStreamer,
        message: TwitchChatMessage,
    ) -> None: ...


class AkatsukiTwitchBot:
    def __init__(
        self,
        *,
        users: UsersRepository,
        twitch_api: TwitchApi,
        twitch_irc: TwitchIrc,
        map_requests: MapRequestHandler,
        max_chat_message_tasks: int = MAX_CHAT_MESSAGE_TASKS,
    ) -> None:
        self.users = users
        self.twitch_api = twitch_api
        self.twitch_irc = twitch_irc
        self.map_requests = map_requests
        self.max_chat_message_tasks = max_chat_message_tasks
        self._streamers_by_channel: dict[str, tuple[LinkedStreamer, ...]] = {}
        self._streamers_lock = asyncio.Lock()
        self._message_tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        sync_task = asyncio.create_task(self._sync_live_channels())
        try:
            async for chat_message in self.twitch_irc.messages():
                self._schedule_chat_message(chat_message)
        finally:
            sync_task.cancel()
            message_tasks = tuple(self._message_tasks)
            for task in message_tasks:
                task.cancel()

            await asyncio.gather(
                sync_task,
                *message_tasks,
                return_exceptions=True,
            )

    def _schedule_chat_message(self, message: TwitchChatMessage) -> None:
        if len(self._message_tasks) >= self.max_chat_message_tasks:
            log.warning(
                "Dropped Twitch chat message.",
                extra={
                    "reason": "message_handler_backlog_full",
                    "channel": message.channel,
                    "author": message.author,
                    "pending_message_handlers": len(self._message_tasks),
                },
            )
            return

        task = asyncio.create_task(self._handle_chat_message(message))
        self._message_tasks.add(task)
        task.add_done_callback(self._message_tasks.discard)

    async def _sync_live_channels(self) -> None:
        while True:
            try:
                streamers = await self.users.fetch_linked_streamers()
                streamers_by_twitch_id: dict[str, list[LinkedStreamer]] = {}
                for streamer in streamers:
                    streamers_by_twitch_id.setdefault(
                        streamer.twitch_account_id,
                        [],
                    ).append(streamer)
                linked_twitch_ids = sorted(streamers_by_twitch_id)
                if settings.TWITCH_REQUIRE_STREAM_ONLINE:
                    logins_by_id = (
                        await self.twitch_api.fetch_live_channel_logins_by_id(
                            linked_twitch_ids,
                        )
                    )
                else:
                    logins_by_id = await self.twitch_api.fetch_user_logins_by_id(
                        linked_twitch_ids,
                    )

                active_streamers = {
                    login: tuple(streamers_by_twitch_id[twitch_id])
                    for twitch_id, login in logins_by_id.items()
                    if twitch_id in streamers_by_twitch_id
                }
                await self._update_cached_twitch_usernames(
                    streamers_by_twitch_id=streamers_by_twitch_id,
                    logins_by_id=logins_by_id,
                )
                async with self._streamers_lock:
                    self._streamers_by_channel = active_streamers

                await self.twitch_irc.sync_channels(set(active_streamers))
                log.info(
                    "Synced Twitch channels.",
                    extra={
                        "linked_channels": len(linked_twitch_ids),
                        "active_channels": len(active_streamers),
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Failed to sync Twitch channels.")

            await asyncio.sleep(settings.TWITCH_POLL_INTERVAL_SECONDS)

    async def _update_cached_twitch_usernames(
        self,
        *,
        streamers_by_twitch_id: dict[str, list[LinkedStreamer]],
        logins_by_id: dict[str, str],
    ) -> None:
        for twitch_id, login in logins_by_id.items():
            streamers = streamers_by_twitch_id.get(twitch_id, [])
            if not streamers:
                continue

            for streamer in streamers:
                if streamer.twitch_login == login:
                    continue

                await self.users.update_twitch_username(
                    user_id=streamer.user_id,
                    twitch_username=login,
                )

    async def _handle_chat_message(self, message: TwitchChatMessage) -> None:
        async with self._streamers_lock:
            streamers = self._streamers_by_channel.get(message.channel, ())

        if not streamers:
            return

        for streamer in streamers:
            try:
                await self.map_requests.handle_chat_message(
                    streamer=streamer,
                    message=message,
                )
            except Exception:
                log.exception(
                    "Failed to handle Twitch chat message.",
                    extra={
                        "channel": message.channel,
                        "author": message.author,
                        "akatsuki_user_id": streamer.user_id,
                    },
                )


async def async_main() -> None:
    configure_logging(settings.LOG_LEVEL)

    users = AkatsukiUsersRepository(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASS,
        database=settings.DB_NAME,
    )
    await users.connect()

    timeout = httpx.Timeout(settings.HTTP_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        akatsuki_api = AkatsukiApiClient(
            http_client,
            base_url=settings.AKATSUKI_API_BASE_URL,
        )
        bancho = BanchoServiceClient(
            http_client,
            base_url=settings.BANCHO_SERVICE_BASE_URL,
            api_key=settings.BANCHO_SERVICE_API_KEY,
        )
        twitch_bot_token_provider = TwitchBotTokenProvider(
            http_client,
            client_id=settings.TWITCH_CLIENT_ID,
            client_secret=settings.TWITCH_CLIENT_SECRET,
            access_token=settings.TWITCH_BOT_OAUTH_TOKEN,
            refresh_token=settings.TWITCH_BOT_REFRESH_TOKEN,
        )
        bot = AkatsukiTwitchBot(
            users=users,
            twitch_api=TwitchApiClient(
                http_client,
                client_id=settings.TWITCH_CLIENT_ID,
                client_secret=settings.TWITCH_CLIENT_SECRET,
            ),
            twitch_irc=TwitchIrcClient(
                username=settings.TWITCH_BOT_USERNAME,
                access_token_provider=twitch_bot_token_provider.get_access_token,
                reconnect_seconds=settings.TWITCH_RECONNECT_SECONDS,
            ),
            map_requests=TwitchMapRequestFeature(
                akatsuki_api=akatsuki_api,
                bancho=bancho,
                rate_limiter=RequestRateLimiter(
                    cooldown_seconds=settings.REQUEST_COOLDOWN_SECONDS,
                    dedupe_seconds=settings.REQUEST_DEDUPE_SECONDS,
                ),
                extract_beatmap_links=extract_beatmap_links,
                format_map_request_message=format_map_request_message,
            ),
        )
        try:
            await bot.run()
        finally:
            users.close()
            await users.wait_closed()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

from __future__ import annotations

import asyncio
import logging

import httpx

from app import settings
from app.clients import AkatsukiApiClient
from app.clients import BanchoServiceClient
from app.clients import TwitchApiClient
from app.irc import TwitchIrcClient
from app.map_requests import TwitchMapRequestFeature
from app.map_requests.formatting import format_map_request_message
from app.map_requests.link_parser import extract_beatmap_links
from app.map_requests.rate_limits import RequestRateLimiter
from app.models import LinkedStreamer
from app.models import TwitchChatMessage
from app.repositories import AkatsukiUsersRepository

log = logging.getLogger(__name__)


class AkatsukiTwitchBot:
    def __init__(
        self,
        *,
        users: AkatsukiUsersRepository,
        twitch_api: TwitchApiClient,
        twitch_irc: TwitchIrcClient,
        map_requests: TwitchMapRequestFeature,
    ) -> None:
        self.users = users
        self.twitch_api = twitch_api
        self.twitch_irc = twitch_irc
        self.map_requests = map_requests
        self._streamers_by_channel: dict[str, LinkedStreamer] = {}
        self._streamers_lock = asyncio.Lock()

    async def run(self) -> None:
        sync_task = asyncio.create_task(self._sync_live_channels())
        try:
            async for chat_message in self.twitch_irc.messages():
                await self._handle_chat_message(chat_message)
        finally:
            sync_task.cancel()
            await asyncio.gather(sync_task, return_exceptions=True)

    async def _sync_live_channels(self) -> None:
        while True:
            try:
                streamers = await self.users.fetch_linked_streamers()
                streamers_by_login = {
                    streamer.twitch_login: streamer for streamer in streamers
                }
                linked_logins = sorted(streamers_by_login)
                if settings.TWITCH_REQUIRE_STREAM_ONLINE:
                    active_logins = await self.twitch_api.fetch_live_channels(
                        linked_logins,
                    )
                else:
                    active_logins = set(linked_logins)

                active_streamers = {
                    login: streamers_by_login[login]
                    for login in active_logins
                    if login in streamers_by_login
                }
                async with self._streamers_lock:
                    self._streamers_by_channel = active_streamers

                await self.twitch_irc.sync_channels(set(active_streamers))
                log.info(
                    "Synced Twitch channels.",
                    extra={
                        "linked_channels": len(linked_logins),
                        "active_channels": len(active_streamers),
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Failed to sync Twitch channels.")

            await asyncio.sleep(settings.TWITCH_POLL_INTERVAL_SECONDS)

    async def _handle_chat_message(self, message: TwitchChatMessage) -> None:
        async with self._streamers_lock:
            streamer = self._streamers_by_channel.get(message.channel)

        if streamer is None:
            return

        await self.map_requests.handle_chat_message(
            streamer=streamer,
            message=message,
        )


async def async_main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

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
        bot = AkatsukiTwitchBot(
            users=users,
            twitch_api=TwitchApiClient(
                http_client,
                client_id=settings.TWITCH_CLIENT_ID,
                client_secret=settings.TWITCH_CLIENT_SECRET,
            ),
            twitch_irc=TwitchIrcClient(
                username=settings.TWITCH_BOT_USERNAME,
                oauth_token=settings.TWITCH_BOT_OAUTH_TOKEN,
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

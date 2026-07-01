from __future__ import annotations

import asyncio
import logging

import httpx

from app import settings
from app.clients import AkatsukiApiClient
from app.clients import BanchoServiceClient
from app.clients import TwitchApiClient
from app.clients import TwitchBotTokenProvider
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
                streamers_by_twitch_id = {
                    streamer.twitch_account_id: streamer for streamer in streamers
                }
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
                    login: streamers_by_twitch_id[twitch_id]
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
                    "Synced Twitch channels: linked=%d active=%d.",
                    len(linked_twitch_ids),
                    len(active_streamers),
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Failed to sync Twitch channels.")

            await asyncio.sleep(settings.TWITCH_POLL_INTERVAL_SECONDS)

    async def _update_cached_twitch_usernames(
        self,
        *,
        streamers_by_twitch_id: dict[str, LinkedStreamer],
        logins_by_id: dict[str, str],
    ) -> None:
        for twitch_id, login in logins_by_id.items():
            streamer = streamers_by_twitch_id.get(twitch_id)
            if streamer is None or streamer.twitch_login == login:
                continue

            await self.users.update_twitch_username(
                user_id=streamer.user_id,
                twitch_username=login,
            )

    async def _handle_chat_message(self, message: TwitchChatMessage) -> None:
        async with self._streamers_lock:
            streamer = self._streamers_by_channel.get(message.channel)

        if streamer is None:
            return

        try:
            await self.map_requests.handle_chat_message(
                streamer=streamer,
                message=message,
            )
        except Exception:
            log.exception(
                "Failed to handle Twitch chat message: channel=%s author=%s "
                "akatsuki_user_id=%d.",
                message.channel,
                message.author,
                streamer.user_id,
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

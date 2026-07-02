from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest

from app.irc import TwitchIrcClient

_REQUIRED_SETTINGS = {
    "APP_ENV": "test",
    "APP_COMPONENT": "akatsuki-twitch-bot",
    "DB_HOST": "localhost",
    "DB_PORT": "3306",
    "DB_USER": "test",
    "DB_PASS": "test",
    "DB_NAME": "test",
    "TWITCH_CLIENT_ID": "test",
    "TWITCH_CLIENT_SECRET": "test",
    "TWITCH_BOT_USERNAME": "osu_akatsuki_bot",
    "TWITCH_BOT_OAUTH_TOKEN": "test",
    "TWITCH_BOT_REFRESH_TOKEN": "test",
    "AKATSUKI_API_BASE_URL": "http://akatsuki-api",
    "BANCHO_SERVICE_BASE_URL": "http://bancho-service-rs-api",
    "BANCHO_SERVICE_API_KEY": "test",
}
for key, value in _REQUIRED_SETTINGS.items():
    os.environ.setdefault(key, value)

from app.main import AkatsukiTwitchBot
from app.models import LinkedStreamer
from app.models import TwitchChatMessage


class SleepingUsersRepository:
    async def fetch_linked_streamers(self) -> list[LinkedStreamer]:
        await asyncio.sleep(3600)
        return []

    async def update_twitch_username(
        self,
        *,
        user_id: int,
        twitch_username: str,
    ) -> None:
        pass


class UnusedTwitchApiClient:
    async def fetch_user_logins_by_id(self, user_ids: list[str]) -> dict[str, str]:
        return {}

    async def fetch_live_channel_logins_by_id(
        self,
        user_ids: list[str],
    ) -> dict[str, str]:
        return {}


class StaticUsersRepository:
    def __init__(self, streamers: list[LinkedStreamer]) -> None:
        self.streamers = streamers
        self.updated_usernames: list[tuple[int, str]] = []

    async def fetch_linked_streamers(self) -> list[LinkedStreamer]:
        return self.streamers

    async def update_twitch_username(
        self,
        *,
        user_id: int,
        twitch_username: str,
    ) -> None:
        self.updated_usernames.append((user_id, twitch_username))


class StaticTwitchApiClient:
    def __init__(self) -> None:
        self.requested_user_ids: list[str] = []

    async def fetch_user_logins_by_id(self, user_ids: list[str]) -> dict[str, str]:
        self.requested_user_ids = user_ids
        return {"1": "streamer"}

    async def fetch_live_channel_logins_by_id(
        self,
        user_ids: list[str],
    ) -> dict[str, str]:
        self.requested_user_ids = user_ids
        return {"1": "streamer"}


class MessageOnlyIrcClient:
    def __init__(self, messages: list[TwitchChatMessage]) -> None:
        self._messages = messages

    async def messages(self) -> AsyncIterator[TwitchChatMessage]:
        for message in self._messages:
            yield message
            await asyncio.sleep(0)

    async def sync_channels(self, channels: set[str]) -> None:
        pass


class RecordingIrcClient:
    def __init__(self) -> None:
        self.synced_channels: set[str] = set()
        self.synced = asyncio.Event()

    async def messages(self) -> AsyncIterator[TwitchChatMessage]:
        await asyncio.sleep(3600)
        yield TwitchChatMessage("unused", "unused", "unused")

    async def sync_channels(self, channels: set[str]) -> None:
        self.synced_channels = channels
        self.synced.set()


class BlockingMapRequests:
    def __init__(self) -> None:
        self.handled_messages: list[str] = []
        self._blocked = asyncio.Event()

    async def handle_chat_message(
        self,
        *,
        streamer: LinkedStreamer,
        message: TwitchChatMessage,
    ) -> None:
        self.handled_messages.append(message.text)
        if message.text == "first":
            await self._blocked.wait()


class RecordingMapRequests:
    def __init__(self) -> None:
        self.handled_user_ids: list[int] = []

    async def handle_chat_message(
        self,
        *,
        streamer: LinkedStreamer,
        message: TwitchChatMessage,
    ) -> None:
        self.handled_user_ids.append(streamer.user_id)


def test_chat_message_handling_does_not_block_irc_reader() -> None:
    async def run() -> None:
        map_requests = BlockingMapRequests()
        bot = AkatsukiTwitchBot(
            users=SleepingUsersRepository(),
            twitch_api=UnusedTwitchApiClient(),
            twitch_irc=MessageOnlyIrcClient(
                [
                    TwitchChatMessage("streamer", "requester", "first"),
                    TwitchChatMessage("streamer", "requester", "second"),
                ],
            ),
            map_requests=map_requests,
            max_chat_message_tasks=2,
        )
        bot._streamers_by_channel = {
            "streamer": (
                LinkedStreamer(
                    user_id=1,
                    username="streamer",
                    twitch_account_id="1",
                    twitch_username="streamer",
                ),
            ),
        }

        await asyncio.wait_for(bot.run(), timeout=1)

        assert map_requests.handled_messages == ["first", "second"]

    asyncio.run(run())


def test_chat_message_handling_drops_messages_when_backlog_is_full() -> None:
    async def run() -> None:
        map_requests = BlockingMapRequests()
        bot = AkatsukiTwitchBot(
            users=SleepingUsersRepository(),
            twitch_api=UnusedTwitchApiClient(),
            twitch_irc=MessageOnlyIrcClient(
                [
                    TwitchChatMessage("streamer", "requester", "first"),
                    TwitchChatMessage("streamer", "requester", "second"),
                ],
            ),
            map_requests=map_requests,
            max_chat_message_tasks=1,
        )
        bot._streamers_by_channel = {
            "streamer": (
                LinkedStreamer(
                    user_id=1,
                    username="streamer",
                    twitch_account_id="1",
                    twitch_username="streamer",
                ),
            ),
        }

        await asyncio.wait_for(bot.run(), timeout=1)

        assert map_requests.handled_messages == ["first"]

    asyncio.run(run())


def test_shared_twitch_link_dispatches_to_each_akatsuki_user() -> None:
    async def run() -> None:
        users = StaticUsersRepository(
            [
                LinkedStreamer(
                    user_id=1,
                    username="first",
                    twitch_account_id="1",
                    twitch_username="old_streamer",
                ),
                LinkedStreamer(
                    user_id=2,
                    username="second",
                    twitch_account_id="1",
                    twitch_username="old_streamer",
                ),
            ],
        )
        twitch_api = StaticTwitchApiClient()
        twitch_irc = RecordingIrcClient()
        map_requests = RecordingMapRequests()
        bot = AkatsukiTwitchBot(
            users=users,
            twitch_api=twitch_api,
            twitch_irc=twitch_irc,
            map_requests=map_requests,
        )

        sync_task = asyncio.create_task(bot._sync_live_channels())
        try:
            await asyncio.wait_for(twitch_irc.synced.wait(), timeout=1)

            await bot._handle_chat_message(
                TwitchChatMessage("streamer", "requester", "map"),
            )
        finally:
            sync_task.cancel()
            await asyncio.gather(sync_task, return_exceptions=True)

        assert twitch_api.requested_user_ids == ["1"]
        assert twitch_irc.synced_channels == {"streamer"}
        assert users.updated_usernames == [(1, "streamer"), (2, "streamer")]
        assert map_requests.handled_user_ids == [1, 2]

    asyncio.run(run())


def test_irc_send_times_out_when_writer_drain_stalls() -> None:
    class StalledWriter(asyncio.StreamWriter):
        def __init__(self) -> None:
            pass

        def __del__(self) -> None:
            pass

        def write(self, data: bytes | bytearray | memoryview[int]) -> None:
            pass

        async def drain(self) -> None:
            await asyncio.sleep(3600)

    async def run() -> None:
        client = TwitchIrcClient(
            username="osu_akatsuki_bot",
            access_token_provider=lambda: _unused_access_token(),
            reconnect_seconds=1,
            write_timeout_seconds=0.001,
        )
        client._writer = StalledWriter()

        with pytest.raises(asyncio.TimeoutError):
            await client._send("PONG :tmi.twitch.tv")

    asyncio.run(run())


async def _unused_access_token() -> str:
    return "unused"

from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable

from app.models import TwitchChatMessage

log = logging.getLogger(__name__)


class TwitchIrcClient:
    def __init__(
        self,
        *,
        username: str,
        access_token_provider: Callable[[], Awaitable[str]],
        reconnect_seconds: int,
        write_timeout_seconds: float = 5.0,
    ) -> None:
        self.username = username.lower()
        self.access_token_provider = access_token_provider
        self.reconnect_seconds = reconnect_seconds
        self.write_timeout_seconds = write_timeout_seconds
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._desired_channels: set[str] = set()
        self._joined_channels: set[str] = set()

    async def messages(self) -> AsyncIterator[TwitchChatMessage]:
        while True:
            try:
                await self._connect()
                while self._reader is not None:
                    line = await self._reader.readline()
                    if not line:
                        raise ConnectionError("Twitch IRC connection closed.")

                    raw_line = line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if raw_line.startswith("PING "):
                        await self._send(raw_line.replace("PING", "PONG", 1))
                        continue

                    message = parse_privmsg(raw_line)
                    if message is not None:
                        yield message
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Twitch IRC connection failed.")
            finally:
                await self._disconnect()

            await asyncio.sleep(self.reconnect_seconds)

    async def sync_channels(self, channels: set[str]) -> None:
        channels = {channel.lower().lstrip("#") for channel in channels}
        self._desired_channels = channels
        if self._writer is None:
            return

        for channel in sorted(channels - self._joined_channels):
            await self._send(f"JOIN #{channel}")
            self._joined_channels.add(channel)
            log.info("Joined Twitch channel.", extra={"channel": channel})

        for channel in sorted(self._joined_channels - channels):
            await self._send(f"PART #{channel}")
            self._joined_channels.remove(channel)
            log.info("Parted Twitch channel.", extra={"channel": channel})

    async def _connect(self) -> None:
        log.info("Connecting to Twitch IRC.")
        access_token = await self.access_token_provider()
        context = ssl.create_default_context()
        self._reader, self._writer = await asyncio.open_connection(
            "irc.chat.twitch.tv",
            6697,
            ssl=context,
        )
        await self._send(f"PASS {_normalize_oauth_token(access_token)}")
        await self._send(f"NICK {self.username}")
        await self._send("CAP REQ :twitch.tv/commands")
        self._joined_channels.clear()
        await self.sync_channels(self._desired_channels)
        log.info("Connected to Twitch IRC.")

    async def _disconnect(self) -> None:
        if self._writer is None:
            return

        self._writer.close()
        await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self._joined_channels.clear()

    async def _send(self, line: str) -> None:
        if self._writer is None:
            raise ConnectionError("Twitch IRC writer is not connected.")

        async with self._write_lock:
            self._writer.write(f"{line}\r\n".encode())
            await asyncio.wait_for(
                self._writer.drain(),
                timeout=self.write_timeout_seconds,
            )


def parse_privmsg(line: str) -> TwitchChatMessage | None:
    if line.startswith("@"):
        _, _, line = line.partition(" ")

    prefix, separator, rest = line.partition(" PRIVMSG ")
    if separator == "":
        return None

    channel, separator, text = rest.partition(" :")
    if separator == "":
        return None

    author = prefix.lstrip(":").split("!", 1)[0]
    return TwitchChatMessage(
        channel=channel.lstrip("#").lower(),
        author=author,
        text=text,
    )


def _normalize_oauth_token(token: str) -> str:
    if token.startswith("oauth:"):
        return token
    return f"oauth:{token}"

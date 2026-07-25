from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinkedStreamer:
    user_id: int
    username: str
    twitch_account_id: str
    twitch_username: str

    @property
    def twitch_login(self) -> str:
        return self.twitch_username.lower()


@dataclass(frozen=True)
class BeatmapLink:
    beatmap_id: int
    url: str
    beatmapset_id: int | None = None


@dataclass(frozen=True)
class BeatmapMetadata:
    beatmap_id: int
    beatmapset_id: int | None
    title: str | None


@dataclass(frozen=True)
class TwitchChatMessage:
    channel: str
    author: str
    text: str


@dataclass(frozen=True)
class DirectMessageResult:
    online: bool
    sent_sessions: int

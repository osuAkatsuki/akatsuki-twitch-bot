from __future__ import annotations

import logging
from collections.abc import Callable

from app.clients import AkatsukiApiClient
from app.clients import BanchoServiceClient
from app.map_requests.rate_limits import RequestRateLimiter
from app.models import BeatmapLink
from app.models import LinkedStreamer
from app.models import TwitchChatMessage

log = logging.getLogger(__name__)


class TwitchMapRequestFeature:
    def __init__(
        self,
        *,
        akatsuki_api: AkatsukiApiClient,
        bancho: BanchoServiceClient,
        rate_limiter: RequestRateLimiter,
        extract_beatmap_links: Callable[[str], list[BeatmapLink]],
        format_map_request_message: Callable[
            [str, int, int | None, str | None],
            str,
        ],
    ) -> None:
        self.akatsuki_api = akatsuki_api
        self.bancho = bancho
        self.rate_limiter = rate_limiter
        self.extract_beatmap_links = extract_beatmap_links
        self.format_map_request_message = format_map_request_message

    async def handle_chat_message(
        self,
        *,
        streamer: LinkedStreamer,
        message: TwitchChatMessage,
    ) -> None:
        beatmap_links = self.extract_beatmap_links(message.text)
        if not beatmap_links:
            return

        beatmap_link = beatmap_links[0]
        if not self.rate_limiter.can_send(streamer.user_id, beatmap_link.beatmap_id):
            log.info(
                "Skipped Twitch beatmap request.",
                extra={
                    "reason": "rate_limited",
                    "channel": message.channel,
                    "author": message.author,
                    "akatsuki_user_id": streamer.user_id,
                    "beatmap_id": beatmap_link.beatmap_id,
                },
            )
            return

        if not await self.bancho.is_online(streamer.user_id):
            log.info(
                "Skipped Twitch beatmap request.",
                extra={
                    "reason": "streamer_offline",
                    "channel": message.channel,
                    "author": message.author,
                    "akatsuki_user_id": streamer.user_id,
                    "beatmap_id": beatmap_link.beatmap_id,
                },
            )
            return

        beatmap_metadata = await self.akatsuki_api.fetch_beatmap_metadata(
            beatmap_link.beatmap_id,
        )
        beatmapset_id = beatmap_link.beatmapset_id
        beatmap_title = None
        if beatmap_metadata is not None:
            beatmapset_id = beatmap_metadata.beatmapset_id or beatmapset_id
            beatmap_title = beatmap_metadata.title

        dm = self.format_map_request_message(
            message.author,
            beatmap_link.beatmap_id,
            beatmapset_id,
            beatmap_title,
        )
        result = await self.bancho.send_aika_dm(user_id=streamer.user_id, message=dm)
        if result.online and result.sent_sessions > 0:
            self.rate_limiter.record(streamer.user_id, beatmap_link.beatmap_id)
            log.info(
                "Forwarded Twitch beatmap request.",
                extra={
                    "channel": message.channel,
                    "author": message.author,
                    "akatsuki_user_id": streamer.user_id,
                    "beatmap_id": beatmap_link.beatmap_id,
                    "sent_sessions": result.sent_sessions,
                },
            )

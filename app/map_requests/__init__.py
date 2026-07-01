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
            [str, int, str | None],
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
                "Skipped Twitch beatmap request due to rate limit: channel=%s "
                "author=%s akatsuki_user_id=%d beatmap_id=%d.",
                message.channel,
                message.author,
                streamer.user_id,
                beatmap_link.beatmap_id,
            )
            return

        if not await self.bancho.is_online(streamer.user_id):
            log.info(
                "Skipped Twitch beatmap request because streamer is offline: "
                "channel=%s author=%s akatsuki_user_id=%d beatmap_id=%d.",
                message.channel,
                message.author,
                streamer.user_id,
                beatmap_link.beatmap_id,
            )
            return

        beatmap_title = await self.akatsuki_api.fetch_beatmap_title(
            beatmap_link.beatmap_id,
        )
        dm = self.format_map_request_message(
            message.author,
            beatmap_link.beatmap_id,
            beatmap_title,
        )
        result = await self.bancho.send_aika_dm(user_id=streamer.user_id, message=dm)
        if result.online and result.sent_sessions > 0:
            self.rate_limiter.record(streamer.user_id, beatmap_link.beatmap_id)
            log.info(
                "Forwarded Twitch beatmap request: channel=%s author=%s "
                "akatsuki_user_id=%d beatmap_id=%d sent_sessions=%d.",
                message.channel,
                message.author,
                streamer.user_id,
                beatmap_link.beatmap_id,
                result.sent_sessions,
            )

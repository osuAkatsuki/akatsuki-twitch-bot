from __future__ import annotations

import asyncio

import httpx

from app.clients import TwitchBotTokenProvider
from app.irc import parse_privmsg
from app.map_requests.formatting import format_map_request_message
from app.map_requests.link_parser import extract_beatmap_links
from app.map_requests.rate_limits import RequestRateLimiter


def test_extracts_osu_and_akatsuki_beatmap_links() -> None:
    text = (
        "try https://osu.ppy.sh/beatmapsets/1#osu/75 " "or https://akatsuki.gg/b/100."
    )

    assert [link.beatmap_id for link in extract_beatmap_links(text)] == [75, 100]


def test_ignores_mapset_links_without_specific_beatmap() -> None:
    assert extract_beatmap_links("https://osu.ppy.sh/s/123") == []


def test_rate_limiter_blocks_cooldown_and_duplicate_map() -> None:
    now = 100.0
    limiter = RequestRateLimiter(
        cooldown_seconds=10,
        dedupe_seconds=60,
        clock=lambda: now,
    )

    assert limiter.can_send(1, 100)
    limiter.record(1, 100)
    assert not limiter.can_send(1, 101)

    now = 111.0
    assert not limiter.can_send(1, 100)
    assert limiter.can_send(1, 101)


def test_parse_twitch_privmsg_with_tags() -> None:
    message = parse_privmsg(
        "@badge-info=;badges= :requester!requester@requester.tmi.twitch.tv "
        "PRIVMSG #streamer :https://osu.ppy.sh/b/75",
    )

    assert message is not None
    assert message.channel == "streamer"
    assert message.author == "requester"
    assert message.text == "https://osu.ppy.sh/b/75"


def test_formats_osu_chat_link() -> None:
    message = format_map_request_message(
        twitch_author="requester",
        beatmap_id=75,
        beatmap_title="Artist - Title [Hard]",
    )

    assert (
        message
        == "Twitch request from requester: [https://osu.ppy.sh/b/75 Artist - Title [Hard]]"
    )


def test_twitch_bot_token_provider_refreshes_user_access_token() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "access_token": "refreshed-access-token",
                    "refresh_token": "refreshed-refresh-token",
                    "expires_in": 3600,
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            provider = TwitchBotTokenProvider(
                http_client,
                client_id="client-id",
                client_secret="client-secret",
                access_token="expired-access-token",
                refresh_token="initial-refresh-token",
            )

            assert await provider.get_access_token() == "refreshed-access-token"
            assert await provider.get_access_token() == "refreshed-access-token"

        assert len(requests) == 1
        body = requests[0].content.decode()
        assert "grant_type=refresh_token" in body
        assert "refresh_token=initial-refresh-token" in body

    asyncio.run(run())

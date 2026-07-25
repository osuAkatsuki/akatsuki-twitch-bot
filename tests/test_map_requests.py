from __future__ import annotations

import asyncio

import httpx

from app.clients import AkatsukiApiClient
from app.clients import TwitchApiClient
from app.clients import TwitchBotTokenProvider
from app.irc import parse_privmsg
from app.map_requests.formatting import format_map_request_message
from app.map_requests.link_parser import extract_beatmap_links
from app.map_requests.rate_limits import RequestRateLimiter


def test_extracts_osu_and_akatsuki_beatmap_links() -> None:
    text = (
        "try https://osu.ppy.sh/beatmapsets/1#osu/75 " "or https://akatsuki.gg/b/100."
    )

    links = extract_beatmap_links(text)

    assert [link.beatmap_id for link in links] == [75, 100]
    assert [link.beatmapset_id for link in links] == [1, None]
    assert [link.url for link in links] == [
        "https://osu.akatsuki.gg/beatmapsets/1#/75",
        "https://akatsuki.gg/b/100",
    ]


def test_extracts_direct_beatmapset_links() -> None:
    text = (
        "https://osu.akatsuki.gg/beatmapsets/1682134#/3530469 "
        '"http://www.osu.ppy.sh/beatmapsets/1/beatmaps/75"'
    )

    links = extract_beatmap_links(text)

    assert [link.beatmap_id for link in links] == [3530469, 75]
    assert [link.beatmapset_id for link in links] == [1682134, 1]
    assert [link.url for link in links] == [
        "https://osu.akatsuki.gg/beatmapsets/1682134#/3530469",
        "https://osu.akatsuki.gg/beatmapsets/1#/75",
    ]


def test_ignores_mapset_links_without_specific_beatmap() -> None:
    assert extract_beatmap_links("https://osu.ppy.sh/s/123") == []
    assert extract_beatmap_links("https://osu.ppy.sh/beatmapsets/123") == []
    assert extract_beatmap_links("https://osu.akatsuki.gg/beatmapsets/123") == []


def test_formats_akatsuki_direct_chat_link() -> None:
    message = format_map_request_message(
        twitch_author="requester",
        beatmap_id=75,
        beatmapset_id=1,
        beatmap_title="Artist - Title [Hard]",
    )

    assert (
        message
        == "Twitch request from requester: [https://osu.akatsuki.gg/beatmapsets/1#/75 Artist - Title [Hard]]"
    )


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


def test_formats_akatsuki_web_chat_link_without_beatmapset_id() -> None:
    message = format_map_request_message(
        twitch_author="requester",
        beatmap_id=75,
        beatmapset_id=None,
        beatmap_title="Artist - Title [Hard]",
    )

    assert (
        message
        == "Twitch request from requester: [https://akatsuki.gg/b/75 Artist - Title [Hard]]"
    )


def test_akatsuki_api_fetches_beatmap_metadata() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/beatmaps"
            assert request.url.params["b"] == "75"
            return httpx.Response(
                200,
                json={
                    "beatmap_id": 75,
                    "beatmapset_id": 1,
                    "song_name": "Artist - Title [Hard]",
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = AkatsukiApiClient(http_client, base_url="https://akatsuki.gg")

            beatmap_metadata = await client.fetch_beatmap_metadata(75)

        assert beatmap_metadata is not None
        assert beatmap_metadata.beatmap_id == 75
        assert beatmap_metadata.beatmapset_id == 1
        assert beatmap_metadata.title == "Artist - Title [Hard]"

    asyncio.run(run())


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


def test_twitch_api_resolves_current_login_by_user_id() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/oauth2/token":
                return httpx.Response(
                    200,
                    json={"access_token": "app-token", "expires_in": 3600},
                )
            assert request.url.path == "/helix/users"
            assert request.url.params.get_list("id") == ["123"]
            return httpx.Response(
                200,
                json={"data": [{"id": "123", "login": "new_login"}]},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = TwitchApiClient(
                http_client,
                client_id="client-id",
                client_secret="client-secret",
            )

            assert await client.fetch_user_logins_by_id(["123"]) == {
                "123": "new_login",
            }

        assert len(requests) == 2

    asyncio.run(run())


def test_twitch_api_fetches_live_channels_by_user_id() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2/token":
                return httpx.Response(
                    200,
                    json={"access_token": "app-token", "expires_in": 3600},
                )
            assert request.url.path == "/helix/streams"
            assert request.url.params.get_list("user_id") == ["123", "456"]
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "user_id": "123",
                            "user_login": "current_login",
                            "type": "live",
                        },
                        {
                            "user_id": "456",
                            "user_login": "offline_channel",
                            "type": "",
                        },
                    ],
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            client = TwitchApiClient(
                http_client,
                client_id="client-id",
                client_secret="client-secret",
            )

            assert await client.fetch_live_channel_logins_by_id(["123", "456"]) == {
                "123": "current_login",
            }

    asyncio.run(run())

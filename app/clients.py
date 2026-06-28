from __future__ import annotations

import time
from typing import Any

import httpx

from app.models import DirectMessageResult


class TwitchApiClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: str,
    ) -> None:
        self.http_client = http_client
        self.client_id = client_id
        self.client_secret = client_secret
        self._app_access_token: str | None = None
        self._app_access_token_expires_at = 0.0

    async def fetch_live_channels(self, logins: list[str]) -> set[str]:
        if not logins:
            return set()

        token = await self._get_app_access_token()
        live_channels: set[str] = set()
        for chunk in _chunks(logins, 100):
            response = await self.http_client.get(
                "https://api.twitch.tv/helix/streams",
                params={"user_login": chunk},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": self.client_id,
                },
            )
            response.raise_for_status()
            payload = response.json()
            for stream in payload.get("data", []):
                if stream.get("type") == "live":
                    live_channels.add(str(stream["user_login"]).lower())

        return live_channels

    async def _get_app_access_token(self) -> str:
        if (
            self._app_access_token is not None
            and time.monotonic() < self._app_access_token_expires_at
        ):
            return self._app_access_token

        response = await self.http_client.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._app_access_token = str(payload["access_token"])
        expires_in = int(payload.get("expires_in", 3600))
        self._app_access_token_expires_at = time.monotonic() + max(60, expires_in - 60)
        return self._app_access_token


class TwitchBotTokenProvider:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        self.http_client = http_client
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._access_token_expires_at = 0.0

    async def get_access_token(self) -> str:
        if time.monotonic() < self._access_token_expires_at - 60:
            return self._access_token

        response = await self.http_client.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = str(payload["access_token"])
        if payload.get("refresh_token"):
            self._refresh_token = str(payload["refresh_token"])

        expires_in = int(payload.get("expires_in", 3600))
        self._access_token_expires_at = time.monotonic() + expires_in
        return self._access_token


class AkatsukiApiClient:
    def __init__(self, http_client: httpx.AsyncClient, *, base_url: str) -> None:
        self.http_client = http_client
        self.base_url = base_url

    async def fetch_beatmap_title(self, beatmap_id: int) -> str | None:
        response = await self.http_client.get(
            f"{self.base_url}/api/v1/beatmaps",
            params={"b": beatmap_id},
        )
        if response.status_code == 404:
            return None

        response.raise_for_status()
        payload = response.json()
        return _optional_str(payload.get("song_name"))


class BanchoServiceClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str,
    ) -> None:
        self.http_client = http_client
        self.base_url = base_url
        self.api_key = api_key

    async def is_online(self, user_id: int) -> bool:
        response = await self.http_client.get(
            f"{self.base_url}/api/v1/isOnline",
            params={"id": user_id},
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("result"))

    async def send_aika_dm(
        self,
        *,
        user_id: int,
        message: str,
    ) -> DirectMessageResult:
        response = await self.http_client.get(
            f"{self.base_url}/api/v1/fokabotDirectMessage",
            params={
                "k": self.api_key,
                "to": user_id,
                "msg": message,
            },
        )
        response.raise_for_status()
        payload = response.json()
        result: dict[str, Any] = payload["result"]
        return DirectMessageResult(
            online=bool(result["online"]),
            sent_sessions=int(result["sent_sessions"]),
        )


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)

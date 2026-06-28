from __future__ import annotations

import os

from dotenv import load_dotenv


def read_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "y"}


def read_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return int(value)


load_dotenv()

APP_ENV = os.environ["APP_ENV"]
APP_COMPONENT = os.environ["APP_COMPONENT"]

DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ["DB_PORT"])
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]
DB_NAME = os.environ["DB_NAME"]

TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
TWITCH_BOT_USERNAME = os.environ["TWITCH_BOT_USERNAME"]
TWITCH_BOT_OAUTH_TOKEN = os.environ["TWITCH_BOT_OAUTH_TOKEN"]
TWITCH_BOT_REFRESH_TOKEN = os.environ["TWITCH_BOT_REFRESH_TOKEN"]
TWITCH_POLL_INTERVAL_SECONDS = read_int("TWITCH_POLL_INTERVAL_SECONDS", 60)
TWITCH_RECONNECT_SECONDS = read_int("TWITCH_RECONNECT_SECONDS", 10)
TWITCH_REQUIRE_STREAM_ONLINE = read_bool(
    os.getenv("TWITCH_REQUIRE_STREAM_ONLINE", "true"),
)

AKATSUKI_API_BASE_URL = os.environ["AKATSUKI_API_BASE_URL"].rstrip("/")
BANCHO_SERVICE_BASE_URL = os.environ["BANCHO_SERVICE_BASE_URL"].rstrip("/")
BANCHO_SERVICE_API_KEY = os.environ["BANCHO_SERVICE_API_KEY"]

REQUEST_COOLDOWN_SECONDS = read_int("REQUEST_COOLDOWN_SECONDS", 30)
REQUEST_DEDUPE_SECONDS = read_int("REQUEST_DEDUPE_SECONDS", 300)
HTTP_TIMEOUT_SECONDS = read_int("HTTP_TIMEOUT_SECONDS", 10)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

from __future__ import annotations


MAX_OSU_CHAT_MESSAGE_LENGTH = 450


def format_map_request_message(
    twitch_author: str,
    beatmap_id: int,
    beatmap_title: str | None,
) -> str:
    title = _sanitize_link_text(beatmap_title or "beatmap")
    author = twitch_author[:25]
    message = (
        f"Twitch request from {author}: [https://akatsuki.gg/b/{beatmap_id} {title}]"
    )
    return message[:MAX_OSU_CHAT_MESSAGE_LENGTH]


def _sanitize_link_text(value: str) -> str:
    return " ".join(value.split())[:180]

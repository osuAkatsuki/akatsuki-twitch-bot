from __future__ import annotations


MAX_OSU_CHAT_MESSAGE_LENGTH = 450


def format_map_request_message(
    twitch_author: str,
    beatmap_id: int,
    beatmapset_id: int | None,
    beatmap_title: str | None,
) -> str:
    title = _sanitize_link_text(beatmap_title or "beatmap")
    author = twitch_author[:25]
    beatmap_url = format_beatmap_url(beatmap_id, beatmapset_id)
    message = f"Twitch request from {author}: [{beatmap_url} {title}]"
    return message[:MAX_OSU_CHAT_MESSAGE_LENGTH]


def format_beatmap_url(beatmap_id: int, beatmapset_id: int | None) -> str:
    if beatmapset_id is None:
        return f"https://akatsuki.gg/b/{beatmap_id}"

    return f"https://osu.akatsuki.gg/beatmapsets/{beatmapset_id}#/{beatmap_id}"


def _sanitize_link_text(value: str) -> str:
    return " ".join(value.split())[:180]

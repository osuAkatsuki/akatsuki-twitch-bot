# Akatsuki Twitch Bot

Standalone Twitch integration service for Akatsuki.

The first feature forwards beatmap links from linked streamers' Twitch chats to
the streamer in-game through Aika while they are live on Twitch and online on
Akatsuki.

## Runtime

```bash
APP_COMPONENT=bot ./scripts/bootstrap.sh
```

Required production secrets live under the `akatsuki-twitch-bot` Vault service.
See `.env.example` for the expected keys.

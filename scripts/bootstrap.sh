#!/usr/bin/env bash
set -eo pipefail

cd /srv/root

if [ -z "$APP_ENV" ]; then
  echo "Please set APP_ENV"
  exit 1
fi

if [ -z "$APP_COMPONENT" ]; then
  echo "Please set APP_COMPONENT"
  exit 1
fi

if [[ $PULL_SECRETS_FROM_VAULT -eq 1 ]]; then
  echo "Fetching secrets from vault"
  akatsuki vault get twitch-bot $APP_ENV -o .env
  echo "Fetched secrets from vault"
  source .env
  echo "Sourced secrets from vault"
fi

if [[ $APP_COMPONENT == "twitch-bot" ]]; then
  exec /scripts/run-bot.sh
else
  echo "Unknown APP_COMPONENT: $APP_COMPONENT"
  exit 1
fi
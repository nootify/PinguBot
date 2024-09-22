# PinguBot
Runs on Python 3.10+ and Discord.py 2.0+

## Requirements
You need to do this or else the bot will not work properly.
1. Login to [Discord](https://discord.com/) and go to your [applications](https://discord.com/developers/applications).
2. Click on your bot, then click on the `Bot` tab on the left.
3. Scroll down to `Privileged Gateway Intents` and enable all intents.

## Setup & Deployment
1. Create a `.env` file with these variables:
```bash
PINGU_PREFIX=?
PINGU_TOKEN=<bot token>

LAVALINK_HOST=audio
LAVALINK_PORT=2333
LAVALINK_PASSWORD=<password here>

# only necessary for local db setup
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<password here>

```
2. Run the bot with:
```bash
docker compose -f docker-compose.local.yml up -d --build
```

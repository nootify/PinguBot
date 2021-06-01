# PinguBot
Runs on Python 3.8+ and Discord.py.

## Requirements
You need to do this or else the bot will not work properly.
1. Login to [Discord](https://discord.com/) and go to your [applications](https://discord.com/developers/applications).
2. Click on your bot, then click on the `Bot` tab on the left.
3. Scroll down to `Privileged Gateway Intents` and enable `Server Members Intent`.

## Setup & Deployment
1. Create a `.env` file in the root folder with these variables:
```bash
PINGU_TOKEN=<bot token>
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<db password>
LAVALINK_PASSWORD=youshallnotpass
LAVALINK_REGION=<discord voice region>
```
- It's highly recommended to change the Lavalink password. Make sure to also change it in `lavalink/application.yml`.
2. Run the bot with:
```bash
docker-compose up -d --build
```
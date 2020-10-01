# PinguBot
Runs on the Discord.py library. Check `requirements.txt` for all the goodies.

## Prerequisites
Discord is changing their API on October 7, 2020. You will need to do this or else the bot will not function as expected.
1. Login to [Discord](https://discord.com/) and go to your [applications](https://discord.com/developers/applications).
2. Click on your bot, then click on the `Bot` tab on the left.
3. Scroll down to `Privileged Gateway Intents` and enable `Server Members Intent`.

## Requirements
1. Clone this repo: `git clone https://github.com/nootify/PinguBot.git`
2. Install Python 3.8 or higher.
- Python 3.7 does not support certain unicode CLDR emoji, a la `\N{large green circle}`.
3. (Optional) Install docker and docker-compose.
- It's highly recommended you use this to simplify deployment.

## Setup
1. Create a `.env` file in the root folder with the following variables:
```bash
PINGU_TOKEN=<your bot token>
PGHOST=db
PGUSER=postgres
PGDATABASE=postgres
PGPASSWORD=<your postgresql password>
POSTGRES_USER=postgres
POSTGRES_DB=postgres
POSTGRES_PASSWORD=<your postgresql password>
LAVALINKHOST=audio
LAVALINKPORT=2333
LAVALINKPASSWORD=<your password>
LAVALINKREGION=<your region>
```
2. Run this in docker-compose to create the docker image:
```bash
docker-compose build
```

## Deployment
1. Run this in docker-compose to deploy PinguBot: 
```bash
docker-compose up -d
```
2. Check the logs by using:
```bash
docker-compose logs bot
```

## TL;DR
1. Make the `.env` file as specified in step 1 of [Setup](#Setup).
2. Run the following to create the image and deploy the bot.
```bash
docker-compose up -d --build
```

# PinguBot
Runs on the Discord.py library. Check `requirements.txt` for all the goodies.

## Requirements
Python 3.8+ and a copy of this repo is required.

Python 3.7 does not support certain unicode CLDR emoji, a la `\N{large green circle}`.

Docker and docker-compose is highly recommended, but not required.

## Installation
Run this in docker-compose to create the image:
```bash
docker-compose build
```

## Deployment
Create a .env file in the root folder with the following variables:
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

Then run this with docker-compose to deploy PinguBot: 
```bash
docker-compose up -d
```

## TL;DR
Install and deploy in one go:
```bash
docker-compose up -d --build
```

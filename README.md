# PinguBot
A simple Discord bot running on the discord.py library.

## Requirements
Python 3.8+, Docker, docker-compose, and a copy of this repo is required.

Python 3.7 does not support unicode CLDR emoji, a la `\N{grinning face with smiling eyes}`.

It's highly recommended to run this in a Docker container, instead of running it manually.

## Installation
Run this in docker-compose to create the image:
```bash
docker-compose build
```

## Deployment
Run this in docker-compose to deploy PinguBot: 
```bash
docker-compose up -d
```

You can also do this to install and deploy in one go:
```bash
docker-compose up -d --build
```

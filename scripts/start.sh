#!/usr/bin/env bash
# Wait until both services are up and the bot can get a connection
while ! nc -z "$POSTGRES_HOST" "$POSTGRES_PORT" ; do
    sleep 1;
    echo "Waiting for Postgres ..."
done
while ! nc -z "$LAVALINK_HOST" "$LAVALINK_PORT" ; do
    sleep 1;
    echo "Waiting for Lavalink ..."
done
python pingu.py

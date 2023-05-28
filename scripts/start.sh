#!/usr/bin/env bash
# Wait until dependent services are up and the bot can get a connection
while ! nc -z "$LAVALINK_HOST" "$LAVALINK_PORT" ; do
    sleep 1;
    echo "Lavalink unavailable - waiting until resource is ready"
done
echo "All services ready"
python pingu.py

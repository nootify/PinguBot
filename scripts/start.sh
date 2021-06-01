#!/usr/bin/env bash
# Wait until both services are up and receiving connections
while ! nc -z "db" 5432 ; do
    sleep 1;
    echo "Waiting for PostgreSQL ..."
done
while ! nc -z "audio" 2333 ; do
    sleep 1;
    echo "Waiting for Lavalink ..."
done
python /pingubot/pingu.py
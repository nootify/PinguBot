#!/usr/bin/env bash
# Ensures the bot does not launch until the database is running
while ! nc -z "$PGHOST" 5432 ; do
    sleep 1;
    # echo "Waiting for PostgreSQL..."
done
while ! nc -z "$LAVALINKHOST" 2333 ; do
    sleep 1;
    # echo "Waiting for Lavalink..."
done
python /pingubot/pingu.py
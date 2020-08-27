#!/usr/bin/env bash
# Ensures the bot does not launch until the database is running
while ! { nc -z "$PGHOST" 5432 || nc -z "$LAVALINKHOST" 2333; }; do
    sleep 1;
    # echo "Waiting for PostgreSQL and Lavalink..."
done
python /pingubot/pingu.py
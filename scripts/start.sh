#!/usr/bin/env bash
# Ensures the bot does not launch until the database is running
while ! nc -z "$PGHOST" 5432; do
    sleep 1;
done
python /pingubot/pingu.py
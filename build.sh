#!/usr/bin/env bash

unset pingutoken
read -s -p "Enter your bot token below (will not be shown in the terminal):"$'\n' pingutoken

echo "secret = \"$pingutoken\"" > pingutoken.py

if [ -f "pingutoken.py" ]; then
	echo "Successfully created pingutoken.py."
else
	echo "Failed to create pingutoken.py (insufficient permissions?)"
	exit 1
fi

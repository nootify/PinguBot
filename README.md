# PinguBot
A simple Discord bot running on the discord.py library

## Requirements
To run PinguBot, Python 3 and a copy of this repo is required.

To run the automatic setup script, a Linux distro with Bash is required.

## Installation
To automatically install and set everything, run the included `setup.sh` script.

### Depedencies
To install the dependencies manually, run the following:
```bash
python -m pip install -r requirements.txt
```
### Environment
To create the environment needed to run the bot manually, create a `.env` file.

Paste the following inside: `export PINGU_TOKEN=<Your token goes here>`

Make sure to replace `<Your token goes here>` with your actual token from the Discord Developer Portal.

Note: Do not add spaces in between the `=` or else your bot will not function.

## Deployment
Assuming you are in the PinguBot directory, run: 
```bash
python pingu.py
```
You're all set! Pingu will automatically retrieve your token from `.env`.

If you need it in your terminal for some reason, you can run the following:
```bash
source .env
```

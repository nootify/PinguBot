FROM python:3.8-slim-buster

WORKDIR /pingubot
COPY . .

RUN apt-get update && \
    # Required for psutil and start.sh
    apt-get install gcc python3-dev netcat -y --no-install-recommends && \
    # Clean up apt-get
    rm -rf /var/lib/apt/lists/* && \
    # In case pip is outdated
    pip install --upgrade pip && \
    # Install required packahes
    pip install -r requirements.txt && \
    # Delete .env that was copied over
    rm -f .env && \
    # Give execution bit to startup script
    chmod +x scripts/start.sh
FROM python:3.8-slim-buster AS build

# Install required base tools for psutil and start.sh
RUN apt-get update && \
    apt-get install gcc python3-dev netcat -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Only re-built if package requirements are updated
WORKDIR /pingubot
COPY ./requirements.txt .
# Install python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

FROM build
COPY . .
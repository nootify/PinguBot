FROM python:3.8-slim-buster AS build

# Install required base tools for psutil and start.sh
RUN apt-get update && \
    apt-get install gcc python3-dev netcat -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    # Add in the Pingu user/group and allow it run instead of root
    groupadd -r -g 999 pingu && \
    useradd -m -r -u 999 -g pingu pingu && \
    # Create the root folder for pingubot
    mkdir /pingubot && \
    chown pingu:pingu /pingubot

# Only rebuild if package requirements are updated
WORKDIR /pingubot
COPY --chown=pingu:pingu ./requirements.txt .
# Install python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt
# Switch to Pingu user/group
USER pingu:pingu

FROM build
COPY --chown=pingu:pingu . .
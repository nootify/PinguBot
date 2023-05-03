FROM fredboat/lavalink:latest

# Default args
ARG LAVALINK_PORT=2333
ARG LAVALINK_PASSWORD=youshallnotpass

# Copy over local sound files
COPY soundfx/ soundfx/

# Copy over the config file
COPY application.yml application.yml

# Temporarily become root to edit the config file
USER root

# Avoids using Docker volume mount
RUN sed -i "s/LAVALINK_PORT/${LAVALINK_PORT}/g" application.yml && \
    sed -i "s/LAVALINK_PASSWORD/${LAVALINK_PASSWORD}/g" application.yml

# Return back to non-root
USER lavalink

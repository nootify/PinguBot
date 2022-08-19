FROM python:3.10-slim AS python-base

    # python
ENV PYTHONUNBUFFERED=1 \
    # prevent python from creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    \
    # pip config
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=1.1.14 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # make poetry create the virtual environment in the project's root
    # it gets named `.venv`
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # do not ask any interactive question
    POETRY_NO_INTERACTION=1 \
    \
    # paths
    # this is where our requirements + virtual environment will live
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

# prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

    # install required packages for psutil and start.sh
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        gcc \
        python3-dev \
        netcat && \
    rm -rf /var/lib/apt/lists/* && \
    \
    # add in the Pingu user and group
    groupadd -g 999 pingu && \
    useradd -r -u 999 -g pingu pingu

# `builder-base` stage is used to build deps + create our virtual environment
FROM python-base as builder-base
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        curl \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

# install poetry - respects $POETRY_VERSION & $POETRY_HOME
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python

# copy project requirement files here to ensure they will be cached.
WORKDIR $PYSETUP_PATH
COPY poetry.lock pyproject.toml ./

# install runtime deps - uses $POETRY_VIRTUALENVS_IN_PROJECT internally
RUN poetry install --no-dev


# `development` image is used during development / testing
FROM python-base as development
# ENV FASTAPI_ENV=development
WORKDIR $PYSETUP_PATH

# copy in our built poetry + venv
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH

# quicker install as runtime deps are already installed
RUN poetry install

# mount point of the code
USER pingu
WORKDIR /opt/pingubot
COPY . .


# `production` image used for runtime
FROM python-base as production
ENV JISHAKU_HIDE=1
COPY --from=builder-base $PYSETUP_PATH $PYSETUP_PATH

USER pingu:pingu
WORKDIR /opt/pingubot
COPY . .

#syntax = docker/dockerfile:1

ARG PYTHON_VERSION="3.10"
ARG POETRY_VERSION="1.8.1"

ARG BUILD_DEPS="\
  gcc bzip2 git curl libpq-dev gettext \
  libgdal-dev python3-cffi python3-gdal \
  python3-dev default-libmysqlclient-dev build-essential \
  build-essential \
  cmake \
  autoconf pkg-config autoconf libtool automake \
  libmariadb-dev"

ARG RUNTIME_DEPS="\
  git \
  tzdata \
  postgresql-client \
  netcat-traditional \
  curl \
  gosu \
  gdal-bin"

FROM python:${PYTHON_VERSION}-slim as base

ARG POETRY_VERSION

ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  DEBIAN_FRONTEND=noninteractive \
  PROJECT=Retail-engine \
  PROJECT_PATH=/home/app \
  APP_USER=app_user \
  APP_GROUP=app_group \
  USER_ID=1999 \
  GROUP_ID=1999 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PATH="/install/bin:${PATH}" \
  APP_PORT=${APP_PORT} \
  APPLICATION_NAME="Retail-engine" \
  RUNTIME_DEPS=${RUNTIME_DEPS} \
  BUILD_DEPS=${BUILD_DEPS} \
  PYTHONIOENCODING=UTF-8 \
  LIBRARY_PATH=/lib:/usr/lib

ARG COMPRESS_ENABLED
ARG BRANDING_ENABLED

RUN addgroup --gid "${GROUP_ID}" "${APP_GROUP}" \
  && useradd --system -m -d "${PROJECT_PATH}" -u "${USER_ID}" -g "${GROUP_ID}" "${APP_USER}"

WORKDIR "${PROJECT_PATH}"

RUN rm -f /etc/apt/apt.conf.d/docker-clean; echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

FROM base as build-poetry

ARG POETRY_VERSION

COPY pyproject.toml poetry.lock ./

RUN --mount=type=cache,mode=0755,target=/pip_cache,id=pip pip install --cache-dir /pip_cache -U poetry=="${POETRY_VERSION}" \
  && poetry cache clear -n --all pypi \
  && poetry export --without-hashes --output requirements.txt
#  && poetry add -n --lock $(cat pip-requires.txt) \

FROM base as build

ARG BUILD_DEPS

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update \
  && apt-get install --no-install-recommends --no-install-suggests -y ${BUILD_DEPS}
 
COPY --from=build-poetry "${PROJECT_PATH}/requirements.txt" /tmp/dep/
RUN --mount=type=cache,mode=0755,target=/pip_cache,id=pip pip install --cache-dir /pip_cache --prefix=/install -r /tmp/dep/requirements.txt

FROM base

ARG BUILD_DEPS
ARG RUNTIME_DEPS

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \
  apt-get update \
  && SUDO_FORCE_REMOVE=yes apt-get remove --purge -y ${BUILD_DEPS} \
  && apt-get autoremove -y \
  && apt-get install -y --no-install-recommends ${RUNTIME_DEPS} \
  && rm -rf /usr/share/man /usr/share/doc

COPY --from=build /install /usr/local
COPY --chown=${APP_USER}:${APP_GROUP} . ${PROJECT_PATH}

RUN ls

USER "${APP_USER}:${APP_GROUP}"
EXPOSE 8000
ENTRYPOINT ["bash", "./docker/entrypoint.sh"]
CMD ["start"]

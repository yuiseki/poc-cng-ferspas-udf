# rio-tiler needs rasterio, which needs GDAL and PROJ. The wheels carry their
# own copies, so a slim base is enough and no system GDAL is installed: a system
# one would be a second PROJ database for rasterio to disagree with, which is
# the failure this project already hit on the development host.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8080 \
    FERSPAS_TILE_CACHE=/tmp/ferspas-tiles \
    FERSPAS_TILE_CACHE_BYTES=268435456

# rasterio's wheel links against libexpat, which slim does not carry. Without
# it `import rasterio` fails at load with "libexpat.so.1: cannot open shared
# object file", which looks nothing like a missing system package.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libexpat1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first so a source change does not re-resolve them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY viewer ./viewer
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Knative sends requests to $PORT and expects the process in the foreground.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn ferspas_tile.app:app --host 0.0.0.0 --port ${PORT}"]

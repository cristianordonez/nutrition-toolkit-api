# BUILD
# First, build the application in the `/app` directory
FROM ghcr.io/astral-sh/uv:trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Omit development dependencies
ENV UV_NO_DEV=1

# Configure the Python directory so it is consistent
ENV UV_PYTHON_INSTALL_DIR=/python

# Only use the managed Python version
ENV UV_PYTHON_PREFERENCE=only-managed

# Install Python before the project for caching
RUN uv python install 3.14

# Install git so that SCM tag can be detected when package is built
RUN apt-get update && apt-get install -y git

# This is a uv workspace, so resolving `--package api` needs every member's
# pyproject.toml present. Copy the tree first, then sync only cloud-api and its
# workspace dependencies -- the desktop engine is not part of this image.
WORKDIR /app
COPY . /app
COPY .git ./.git/
# `--group migrations` is explicit because UV_NO_DEV=1 drops dev groups, and
# the migrate service needs alembic, which lives in that group rather than in
# cloud-api's own dependencies.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package api --group migrations


# PRODUCTION
# Then, use a final image without uv
FROM debian:trixie-slim

# Setup a non-root user
RUN groupadd --system --gid 999 nonroot \
    && useradd --system --gid 999 --uid 999 --create-home nonroot

# Copy the Python version
COPY --from=builder /python /python

# Copy the application from the builder
COPY --from=builder --chown=nonroot:nonroot /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Use the non-root user to run our application
USER nonroot

# Use `/app` as the working directory
WORKDIR /app

# Run the FastAPI application by default. 0.0.0.0 so the port is reachable
# from outside the container.
CMD ["api-server", "--host", "0.0.0.0", "--port", "8000"]

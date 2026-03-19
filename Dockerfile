# Use the official uv image for blazing-fast builds
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Enable bytecode compilation and disable cache for smaller image
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy pyproject.toml and lockfile (if exists)
COPY pyproject.toml uv.lock* /app/

# Install dependencies first (so they are cached via Docker layers)
RUN uv sync --frozen --no-install-project || uv sync --no-install-project

# Copy the rest of the application code
COPY . /app

# Install the project itself
RUN uv sync --frozen || uv sync

# FastMCP SSE server port
EXPOSE 8000

# Tell Railway what command to run
# We use sh -c to run the database setup BEFORE the main server starts
CMD ["sh", "-c", "uv run python setup_db.py && uv run python main.py"]


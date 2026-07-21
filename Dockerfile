FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.1 /uv /uvx /bin/

WORKDIR /app

# Install the locked runtime environment.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY metadata_tool/ metadata_tool/
COPY provider/ provider/

ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 32500

# Run the provider
CMD ["uvicorn", "provider.main:app", "--host", "0.0.0.0", "--port", "32500"]

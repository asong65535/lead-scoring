# syntax=docker/dockerfile:1

# ============================================
# Builder Stage
# ============================================
FROM python:3.13-slim as builder

# Install Poetry
ENV POETRY_VERSION=2.3.2
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VENV=/opt/poetry-venv
ENV POETRY_CACHE_DIR=/opt/.cache

RUN python -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install -U pip setuptools \
    && $POETRY_VENV/bin/pip install poetry==$POETRY_VERSION \
    && $POETRY_VENV/bin/poetry self add poetry-plugin-export

ENV PATH="${POETRY_VENV}/bin:${PATH}"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Export dependencies to requirements.txt (no dev deps)
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --without dev

# ============================================
# Runtime Stage
# ============================================
FROM python:3.13-slim as runtime

# Create non-root user
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from builder
COPY --from=builder /app/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appgroup . .

# Create directories for models and data
RUN mkdir -p models data logs \
    && chown -R appuser:appgroup models data logs

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

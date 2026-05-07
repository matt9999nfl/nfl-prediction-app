FROM python:3.11-slim

WORKDIR /app

# Build-time arg so GIT_COMMIT is baked into the image and surfaced by /health.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

# Install dependencies before copying source so layer is cached on dep changes.
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir ".[dev]" 2>/dev/null || pip install --no-cache-dir .

COPY app/ ./app/

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]

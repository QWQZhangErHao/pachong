# Multi-stage production Docker image for Pachong
# Stage 1: Builder
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
COPY pachong/ pachong/
COPY config/ config/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r pachong && useradd -r -g pachong pachong

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/pachong pachong/
COPY --from=builder /app/config config/
COPY --from=builder /app/pyproject.toml .

RUN chown -R pachong:pachong /app
USER pachong

ENV PYTHONUNBUFFERED=1
ENV PACHONG_ENV=production

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: run the API server
EXPOSE 8000
CMD ["python", "-m", "pachong.cli.main", "api"]

# Alternative entrypoints (override CMD):
#   Scheduler: python -m pachong.cli.main scheduler
#   Worker:    python -m pachong.cli.main worker

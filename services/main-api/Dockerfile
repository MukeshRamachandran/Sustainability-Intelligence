FROM python:3.12.11-slim-bookworm

ARG INSTALL_DEV=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 microcosm \
    && useradd --system --uid 10001 --gid microcosm --home-dir /app microcosm \
    && mkdir -p /data/evidence/quarantine /data/evidence/clean /app/certificate-storage \
    && chown -R microcosm:microcosm /app /data/evidence

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests

RUN pip install --upgrade "pip==25.2" \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install ".[dev]"; else pip install .; fi

USER microcosm

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

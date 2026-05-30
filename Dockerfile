# syntax=docker/dockerfile:1.7

# ---- Stage 1: builder ----
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependencies in a dedicated venv so the runtime stage gets a clean copy
# without the build toolchain (much smaller final image).
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TADQEEQ_DATA_DIR=/data/corpus \
    CHAT_HISTORY_DIR=/data/chat_history \
    LIBRARY_CHAT_HISTORY_DIR=/data/library_chat_history \
    ANALYSIS_DOCS_DIR=/data/analysis_documents \
    SETTINGS_FILE=/data/settings.json

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app app/ ./app/
COPY --chown=app:app pyproject.toml requirements.txt README.md ./

# /data is the writable mount (chat history, settings, uploaded documents)
# /data/corpus is the read-only mount for the v3.x corpus (chroma_db_v2,
# bm25_index.pkl, documents.json, clauses.json)
RUN mkdir -p /data /data/corpus && chown -R app:app /data

USER app

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8765/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]

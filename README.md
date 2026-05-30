# tadqeeq-backend

Bilingual (EN/AR) Islamic finance RAG service backend for Saudi (SAMA + CMA) compliance.

Part of the TadqeeqAI v4 architecture:

| Repo | Role |
|---|---|
| **tadqeeq-backend** | FastAPI service. Hybrid retrieval (BM25 + semantic), LLM provider abstraction (Claude / Ollama), document analysis, exports. |
| tadqeeq-web | React + Vite + TypeScript web frontend. |
| tadqeeq-desktop | Tauri desktop wrapper, ships with local Ollama for data sovereignty. |

Predecessor: [TadqeeqAI](https://github.com/M-AlAteegi/TadqeeqAI) (v3.x, PyWebView desktop app — archived).

## Quickstart (Python)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env  # then edit CLAUDE_API_KEY
uvicorn app.main:app --port 8765
```

Open <http://localhost:8765/docs> for the OpenAPI UI, or <http://localhost:8765/health> for a quick sanity check.

## Quickstart (Docker)

Assumes Docker Desktop installed and the sibling `TadqeeqAI` v3.x repo
sits at `../TadqeeqAI/` (for the corpus). Override `TADQEEQ_CORPUS_PATH`
to point elsewhere.

```bash
# Set your Claude key in the environment (or in a .env beside the compose file)
export CLAUDE_API_KEY=sk-ant-...

docker compose up --build
```

The compose file mounts `./data` for writable state (chat history,
settings, uploaded documents) and `${TADQEEQ_CORPUS_PATH}` read-only
for the SAMA/CMA corpus.

To run against local Ollama from inside the container, set
`LLM_PROVIDER=ollama`; the container reaches the host's Ollama via
`host.docker.internal:11434` (already configured).

## Auth + rate limits

- Set `API_KEY=<some-secret>` in `.env` (or compose `environment:`) to
  require `Authorization: Bearer <some-secret>` on every `/api/*`
  endpoint. `/health` stays open. Empty by default for dev.
- Per-endpoint rate limits (`RATE_LIMIT_CHAT`, `RATE_LIMIT_LIBRARY`,
  `RATE_LIMIT_BRIEF`, `RATE_LIMIT_UPLOAD`) are env-driven; defaults
  are sized for solo dev and should be tightened for public deploys.

## Architecture

```
app/
├── main.py          FastAPI entry, CORS, lifespan
├── config.py        pydantic-settings (env-driven)
├── api/             HTTP routers (chat, library, analysis, exports, settings, health)
├── core/            Business logic (rag, library, history, analysis, exports)
├── providers/       LLM provider abstraction (base ABC, ClaudeProvider, OllamaProvider)
└── models/          Pydantic request/response shapes
```

LLM provider is selected at startup via `LLM_PROVIDER` env var. The same RAG pipeline runs on top of either Claude (cloud) or Ollama (local) — the only difference is the synthesis step.

## Tech stack

FastAPI · Pydantic · ChromaDB · BM25 · sentence-transformers (`intfloat/multilingual-e5-base`) · Anthropic SDK (Haiku 4.5) · Ollama (Aya 8B) · PyMuPDF · python-docx · ReportLab · Docker

# tadqeeq-backend

Bilingual (EN/AR) Islamic finance RAG service backend for Saudi (SAMA + CMA) compliance.

Part of the TadqeeqAI v4 architecture:

| Repo | Role |
|---|---|
| **tadqeeq-backend** | FastAPI service. Hybrid retrieval (BM25 + semantic), LLM provider abstraction (Claude / Ollama), document analysis, exports. |
| tadqeeq-web | React + Vite + TypeScript web frontend. |
| tadqeeq-desktop | Tauri desktop wrapper, ships with local Ollama for data sovereignty. |

Predecessor: [TadqeeqAI](https://github.com/M-AlAteegi/TadqeeqAI) (v3.x, PyWebView desktop app — archived).

## Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env  # then edit CLAUDE_API_KEY
uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs> for the OpenAPI UI, or <http://localhost:8000/health> for a quick sanity check.

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

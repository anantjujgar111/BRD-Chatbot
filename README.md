# BRD Chatbot

A multi-file Excel chatbot for **Business Requirements Document (BRD)** generation. Upload many messy spreadsheets, ask questions with hybrid semantic retrieval, and generate structured BRD drafts with source citations.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js (Node) |
| API Gateway | Express (Node) |
| Processing & RAG | FastAPI (Python) |
| Metadata DB | SQLite (local) |
| Vector Search | ChromaDB (local) |
| LLM | Claude (Anthropic API) |

## Features

- Upload **multiple Excel/CSV files** in one batch
- Parse **unstructured/messy Excel** (merged cells, irregular blocks)
- **Hybrid retrieval** on every query (semantic + keyword/BM25)
- Chat Q&A with **file + sheet + cell citations**
- **Full BRD generation** with standard sections
- Local storage only — no PostgreSQL required for MVP

## Sample Input Files

Ready-made test files are in `samples/excel/`:

- **Structured:** functional requirements, stakeholders matrix, NFR CSV
- **Unstructured:** client notes, workshop capture, legacy export

See `samples/README.md` for details and suggested test questions.

## Quick Start

### 1. Setup

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### 2. Configure

Edit `.env` and set:

```env
ANTHROPIC_API_KEY=your_key_here
```

Optional model override:

```env
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

### 3. Run (3 terminals)

**Terminal 1 — Python processor**
```bash
source services/python-processor/.venv/bin/activate
cd services/python-processor
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Node API**
```bash
npm run dev --prefix apps/api
```

**Terminal 3 — Web UI**
```bash
npm run dev --prefix apps/web
```

Open **http://localhost:3000**

## Usage

1. Upload one or more `.xlsx`, `.xls`, or `.csv` files
2. Wait until files show status **indexed**
3. Ask questions in chat (retrieval runs automatically per query)
4. Click **Generate Full BRD** for a complete draft

## API Endpoints

### Node gateway (`http://localhost:3001`)

- `GET /health`
- `POST /workspaces`
- `POST /workspaces/:id/upload`
- `GET /workspaces/:id/files`
- `GET /workspaces/:id/stats`
- `POST /chat`
- `POST /brd/generate`

### Python service (`http://localhost:8000/api`)

Same routes under `/api/*` — used internally by the gateway.

## Project Structure

```
apps/
  api/          # Node Express gateway
  web/          # Next.js UI
services/
  python-processor/   # FastAPI ingest + RAG + BRD
data/
  uploads/      # Uploaded Excel files
  chroma/       # Local vector index
  brd.db        # SQLite metadata (created at runtime)
```

## Notes

- Without `ANTHROPIC_API_KEY`, ingestion and retrieval still work; generation returns retrieved context only.
- Semantic search uses ChromaDB's local embeddings — no separate embedding API key required.
- PostgreSQL can be added later by swapping the storage layer — retrieval logic stays the same.
- BRD output is a draft; human review is recommended for production use.

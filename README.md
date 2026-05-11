# Basit AI

Your personal AI co-pilot. Chainlit UI · LangGraph + GPT-4o · Postgres-backed threads + long-term memory · Backblaze B2 file storage · Google OAuth.

## Architecture

```
Browser ──Google OAuth──▶ Chainlit (FastAPI/Starlette)
                              │
                              ├─▶ LangGraph workflow (graph/workflow.py)
                              │     ├─ chat_node  (GPT-4o, streaming)
                              │     └─ tools      (Tavily, calculator, RAG)
                              │              │
                              │              └─▶ Chroma (services/rag.py)
                              │
                              ├─▶ AsyncPostgresSaver  ─┐
                              │   (LangGraph state)    │
                              │                        ├─▶ Postgres
                              ├─▶ SQLAlchemyDataLayer ─┘   (Supabase)
                              │   (threads / steps / elements / feedback)
                              │
                              └─▶ S3StorageClient ───────▶ Backblaze B2
                                  (file uploads)
```

## Local development

```bash
# 1. Python env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure env
cp .env.example .env
chainlit create-secret           # paste output into CHAINLIT_AUTH_SECRET
# fill OPENAI_API_KEY, TAVILY_API_KEY, DATABASE_URL,
# OAUTH_GOOGLE_CLIENT_ID, OAUTH_GOOGLE_CLIENT_SECRET, B2_*

# 3. Apply schema to Neon (only the first time)
python -c "import os, psycopg; from dotenv import load_dotenv; load_dotenv(); \
url = os.environ['DATABASE_URL'].replace('-pooler.', '.', 1); \
psycopg.connect(url, autocommit=True).cursor().execute(open('init.sql').read())"

# 4. Run
chainlit run app.py -w
```

Open <http://localhost:8000> and sign in with Google.

## Going live

See [DEPLOY.md](./DEPLOY.md) — Supabase + Backblaze B2 + Koyeb (free).

## Project layout

```
app.py                 # Chainlit entrypoint (lifecycle, OAuth, data layer)
core/
  config.py            # Env-driven config (single source of truth)
graph/
  tools.py             # @tool definitions (web, calculator, jobs, RAG)
  workflow.py          # LangGraph state graph + system prompt
services/
  rag.py               # RAG service (Chroma + GPT-4o vision)
init.sql               # Chainlit 2.11 data-layer schema (run once on Neon)
.chainlit/config.toml  # UI config
Dockerfile             # Production image (Koyeb)
```

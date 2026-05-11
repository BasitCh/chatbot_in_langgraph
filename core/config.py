"""Centralised env-driven configuration. Imported by every layer.

All values are read once at import time so misconfiguration fails fast on
startup rather than mid-conversation.
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# --- LLM / search ---------------------------------------------------------
OPENAI_API_KEY = _required("OPENAI_API_KEY")
TAVILY_API_KEY = _required("TAVILY_API_KEY")

# --- Postgres -------------------------------------------------------------
# We always connect to Neon's *direct* endpoint (session-mode), not the
# `-pooler` endpoint (transaction-mode pgbouncer). LangGraph and Chainlit
# both want long-lived connections + prepared statements; transaction-mode
# pooling breaks prepared statements with `DuplicatePreparedStatementError`.
# So we transparently rewrite the host to drop `-pooler` if present — the
# user can paste either URL into .env without thinking about it.
_RAW_DATABASE_URL = _required("DATABASE_URL")


def _to_direct_url(url: str) -> str:
    return url.replace("-pooler.", ".", 1)


# psycopg dialect — used by LangGraph's AsyncPostgresSaver.
DATABASE_URL = _to_direct_url(_RAW_DATABASE_URL)


def _to_asyncpg_url(url: str) -> str:
    """SQLAlchemy + asyncpg URL.

    Strips libpq-only query params (sslmode, channel_binding, options) that
    asyncpg rejects, and translates the scheme.
    """
    base, _, query = url.partition("?")
    if base.startswith("postgresql://"):
        base = "postgresql+asyncpg://" + base[len("postgresql://"):]
    elif base.startswith("postgres://"):
        base = "postgresql+asyncpg://" + base[len("postgres://"):]
    keep = []
    for part in query.split("&") if query else []:
        if not part:
            continue
        key = part.split("=", 1)[0].lower()
        if key in {"sslmode", "channel_binding", "options"}:
            continue
        keep.append(part)
    return base + ("?" + "&".join(keep) if keep else "")


DATABASE_URL_ASYNCPG = _to_asyncpg_url(DATABASE_URL)

# --- Backblaze B2 (S3-compatible) -----------------------------------------
B2_BUCKET = _required("B2_BUCKET")
B2_ENDPOINT = _required("B2_ENDPOINT")  # e.g. https://s3.us-east-005.backblazeb2.com
B2_ACCESS_KEY = _required("B2_ACCESS_KEY")
B2_SECRET_KEY = _required("B2_SECRET_KEY")

# Derive region from the endpoint hostname (e.g. "us-east-005") so users
# don't have to set it twice. Falls back to a sane default.
_region_match = re.search(r"s3\.([a-z0-9-]+)\.backblazeb2\.com", B2_ENDPOINT)
B2_REGION = os.environ.get("B2_REGION") or (
    _region_match.group(1) if _region_match else "us-west-002"
)

# --- RAG ------------------------------------------------------------------
CHROMA_PERSIST_DIR = os.environ.get(
    "CHROMA_PERSIST_DIR",
    str(Path(".data/chroma").resolve()),
)

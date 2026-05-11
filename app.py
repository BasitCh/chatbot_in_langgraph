"""Chainlit entrypoint.

Three things happen here that are worth understanding:

1. PERSISTENCE
   One AsyncConnectionPool feeds both:
     - AsyncPostgresSaver  -> per-thread conversation state (LangGraph checkpoints)
     - AsyncPostgresStore  -> cross-thread long-term memory (per user_id)
   Both are set up once on the first chat and reused forever.

2. HUMAN-IN-THE-LOOP
   The workflow is compiled with `interrupt_before=["tools"]`. After the
   LLM proposes tool calls, the graph stops; we surface them to the user
   with Approve/Reject buttons. "Safe" read-only tools (RAG, calculator,
   memory) auto-approve so the chat stays snappy.

3. UI TOOL VISIBILITY
   `cl.LangchainCallbackHandler` is passed in the runnable config. It
   converts every LangChain run (LLM call, tool call) into a nested
   chainlit Step, so the user sees what the agent is doing.
"""

import asyncio
import logging
import os

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.data.storage_clients.s3 import S3StorageClient
from chainlit.langchain.callbacks import LangchainCallbackHandler
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from core.config import (
    B2_ACCESS_KEY,
    B2_BUCKET,
    B2_ENDPOINT,
    B2_REGION,
    B2_SECRET_KEY,
    DATABASE_URL,
    DATABASE_URL_ASYNCPG,
)
from graph.workflow import workflow
from services.rag import get_rag

logger = logging.getLogger("chatbot")
logger.setLevel(logging.INFO)


# Tools that don't need user approval (read-only or local). Anything not
# in this set will trigger a HITL prompt before running.
AUTO_APPROVE_TOOLS = {
    "search_uploaded_documents",
    "calculator",
    "save_memory",
    "list_memories",
}


# --- One-time persistence init -------------------------------------------
_init_lock = asyncio.Lock()
_pool: AsyncConnectionPool | None = None
_chatbot = None


async def _ensure_chatbot():
    """Open the pool, set up saver + store, compile the graph. Idempotent."""
    global _pool, _chatbot
    if _chatbot is not None:
        return _chatbot
    async with _init_lock:
        if _chatbot is not None:
            return _chatbot
        _pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            min_size=2,
            max_size=20,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _pool.open()

        saver = AsyncPostgresSaver(_pool)
        await saver.setup()

        store = AsyncPostgresStore(_pool)
        await store.setup()

        _chatbot = workflow.compile(
            checkpointer=saver,
            store=store,
            interrupt_before=["tools"],
        )
    return _chatbot


# --- Chainlit data layer (threads / steps / elements / feedback) ----------
@cl.data_layer
def _data_layer():
    storage = S3StorageClient(
        bucket=B2_BUCKET,
        endpoint_url=B2_ENDPOINT,
        aws_access_key_id=B2_ACCESS_KEY,
        aws_secret_access_key=B2_SECRET_KEY,
        region_name=B2_REGION,
    )
    return SQLAlchemyDataLayer(
        conninfo=DATABASE_URL_ASYNCPG,
        ssl_require=True,
        storage_provider=storage,
    )


# --- Auth: any Google account ---------------------------------------------
@cl.oauth_callback
def oauth_callback(provider_id: str, token: str, raw_user_data: dict, default_user: cl.User):
    if provider_id != "google":
        return None
    email = (raw_user_data.get("email") or "").lower()
    if not email:
        return None
    return cl.User(
        identifier=email,
        metadata={
            "name": raw_user_data.get("name"),
            "picture": raw_user_data.get("picture"),
            "provider": "google",
        },
    )


# --- Lifecycle ------------------------------------------------------------
@cl.on_chat_start
async def on_chat_start():
    await _ensure_chatbot()


@cl.on_chat_resume
async def on_chat_resume(thread):
    await _ensure_chatbot()


# --- Helpers --------------------------------------------------------------
def _user_id() -> str:
    """The email of the signed-in Google user — used as the long-term memory key."""
    user = cl.user_session.get("user")
    return getattr(user, "identifier", "default") if user else "default"


def _format_tool_call(tc: dict) -> str:
    args = tc.get("args", {})
    arg_preview = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
    return f"`{tc['name']}({arg_preview})`"


async def _ingest_uploads(message: cl.Message) -> list[str]:
    """Index attached files into RAG so the agent can query them this turn."""
    if not message.elements:
        return []
    rag = get_rag()
    candidates = [
        el for el in message.elements
        if getattr(el, "path", None) and os.path.exists(el.path)
    ]
    results = await asyncio.gather(
        *[asyncio.to_thread(rag.ingest, el.path, el.name) for el in candidates],
        return_exceptions=True,
    )
    indexed = []
    for el, res in zip(candidates, results):
        if isinstance(res, Exception):
            logger.exception("RAG ingest failed for %s: %r", el.name, res)
            await cl.Message(content=f"⚠️ Could not index `{el.name}`: {res}").send()
        else:
            logger.info("RAG ingest OK: %s -> %d chunks", el.name, res)
            indexed.append(el.name)
    return indexed


async def _request_approval(tool_calls: list[dict]) -> bool:
    """Ask the user to approve the pending tool calls. Returns True if approved."""
    summary = "\n".join(f"• {_format_tool_call(tc)}" for tc in tool_calls)
    res = await cl.AskActionMessage(
        content=f"The assistant wants to run:\n{summary}\n\nApprove?",
        actions=[
            cl.Action(name="approve", payload={"v": "ok"}, label="✅ Approve"),
            cl.Action(name="reject", payload={"v": "no"}, label="❌ Reject"),
        ],
        timeout=120,
    ).send()
    return bool(res) and res.get("payload", {}).get("v") == "ok"


# --- Message handler -------------------------------------------------------
@cl.on_message
async def on_message(message: cl.Message):
    chatbot = await _ensure_chatbot()
    thread_id = cl.context.session.thread_id

    indexed = await _ingest_uploads(message)
    user_content = message.content
    if indexed:
        user_content += (
            f"\n\n[Attached files indexed this turn: {', '.join(indexed)}. "
            f"Use search_uploaded_documents to query them.]"
        )

    config = {
        "configurable": {"thread_id": thread_id, "user_id": _user_id()},
        # LangchainCallbackHandler renders every LLM/tool run as a nested
        # chainlit Step so the user sees what the agent is doing.
        "callbacks": [LangchainCallbackHandler()],
    }

    # Drive the graph until it terminates (or until the user rejects a tool).
    # `None` as input means "resume from where the last interrupt paused".
    graph_input: dict | None = {"messages": [HumanMessage(content=user_content)]}

    while True:
        await chatbot.ainvoke(graph_input, config=config)

        state = await chatbot.aget_state(config)
        if "tools" not in state.next:
            break  # Graph finished, no pending tool calls.

        # Graph paused because the LLM proposed tool calls. Decide whether
        # to auto-approve or ask the user.
        last_msg = state.values["messages"][-1]
        tool_calls: list[dict] = list(getattr(last_msg, "tool_calls", []) or [])

        if all(tc["name"] in AUTO_APPROVE_TOOLS for tc in tool_calls):
            graph_input = None  # Auto-approve, resume.
            continue

        if await _request_approval(tool_calls):
            graph_input = None  # User approved, resume.
        else:
            # Rejected: inject a ToolMessage for each pending call so the
            # LLM sees the rejection and can apologise / try another path.
            rejections = [
                ToolMessage(content="User rejected this tool call.", tool_call_id=tc["id"])
                for tc in tool_calls
            ]
            await chatbot.aupdate_state(
                config, {"messages": rejections}, as_node="tools"
            )
            graph_input = None

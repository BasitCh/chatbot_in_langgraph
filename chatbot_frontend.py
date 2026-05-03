import os
import chainlit as cl
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv

from chatbot_backend import workflow

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

# Shared connection pool used by the LangGraph Postgres checkpointer.
# Lazily opened on the first chat session and reused across sessions.
_pool: AsyncConnectionPool | None = None
_setup_done = False


async def get_checkpointer() -> AsyncPostgresSaver:
    global _pool, _setup_done
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            max_size=20,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _pool.open()
    saver = AsyncPostgresSaver(_pool)
    if not _setup_done:
        await saver.setup()
        _setup_done = True
    return saver


@cl.oauth_callback
def oauth_callback(provider_id, token, raw_user_data, default_user):
    if provider_id == "google":
        return cl.User(identifier=raw_user_data.get("email"))
    return None


@cl.on_chat_start
async def start():
    checkpointer = await get_checkpointer()
    chatbot = workflow.compile(checkpointer=checkpointer)
    cl.user_session.set("chatbot", chatbot)


@cl.on_chat_resume
async def resume(thread):
    checkpointer = await get_checkpointer()
    chatbot = workflow.compile(checkpointer=checkpointer)
    cl.user_session.set("chatbot", chatbot)


@cl.on_message
async def main(message: cl.Message):
    chatbot = cl.user_session.get("chatbot")
    thread_id = cl.context.session.thread_id

    config = {"configurable": {"thread_id": thread_id}}
    msg = cl.Message(content="")

    async for event in chatbot.astream_events(
        {"messages": [HumanMessage(content=message.content)]},
        config,
        version="v2",
    ):
        if event["event"] == "on_chat_model_stream":
            token = event["data"]["chunk"].content
            if token:
                if not msg.id:
                    await msg.send()
                await msg.stream_token(token)
    await msg.update()

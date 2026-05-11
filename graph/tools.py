"""Tools the agent can call.

Each `@tool` is bound to the LLM in graph/workflow.py and exposed as a
function-call. Three categories:

  * Pure utility   — calculator (no I/O)
  * External       — Tavily web search, LinkedIn job search
  * Context-aware  — search_uploaded_documents (RAG), save_memory /
                     list_memories (cross-thread long-term memory)

The memory tools use LangGraph's `InjectedStore`: at runtime LangGraph
injects the shared `BaseStore` instance into the tool call, scoped per
user via `config["configurable"]["user_id"]`.
"""

import uuid
from typing import Annotated

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

from services.rag import get_rag


@tool
def calculator(first_num: float, second_num: float, operation: str) -> dict:
    """Perform basic arithmetic. Supported operations: add, mul, sub, div."""
    try:
        match operation:
            case "add":
                result = first_num + second_num
            case "sub":
                result = first_num - second_num
            case "mul":
                result = first_num * second_num
            case "div":
                if second_num == 0:
                    return {"error": "Division by zero is not allowed"}
                result = first_num / second_num
            case _:
                return {"error": f"Unsupported operation {operation}"}
        return {"first_number": first_num, "second_number": second_num, "result": result}
    except Exception as e:
        return {"error": str(e)}


@tool
def search_linkedin_jobs(job_title: str, location: str):
    """Search LinkedIn for active job posts matching a title and location."""
    query = f"site:linkedin.com/jobs/view '{job_title}' in {location}"
    return TavilySearchResults(max_results=5).invoke(query)


@tool
def search_uploaded_documents(query: str) -> str:
    """Retrieve relevant excerpts from files the user uploaded (PDF, DOCX, TXT, images).

    Call this whenever the user references their uploads — phrases like "the
    document", "the PDF", "the image", "what I just sent", a filename, or any
    question that is likely answered by uploaded content rather than general
    knowledge. The query should be the user's information need rephrased as a
    short search string. The tool returns the top-matching chunks; ground your
    answer in them.
    """
    return get_rag().retrieve(query)


# --- Long-term memory ----------------------------------------------------
#
# Memories live in LangGraph's `BaseStore` (backed by AsyncPostgresStore).
# They survive across threads — anything you `save_memory` here is visible
# in every future conversation with this same user.
#
# Namespace convention: ("memories", user_id)


@tool
async def save_memory(
    fact: str,
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore()],
) -> str:
    """Save a single durable fact about the user to long-term memory.

    Call this when the user shares information you should remember across
    conversations: their name, role, ongoing projects, preferences, goals,
    relationships, etc. ONE fact per call — split compound info into
    separate calls. Don't save ephemeral turn-local context (e.g. "user is
    currently asking about X").
    """
    user_id = config["configurable"].get("user_id", "default")
    await store.aput(
        ("memories", user_id),
        str(uuid.uuid4()),
        {"fact": fact},
    )
    return f"Saved to memory: {fact}"


@tool
async def list_memories(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore()],
) -> str:
    """List every long-term memory you have saved about the user."""
    user_id = config["configurable"].get("user_id", "default")
    items = await store.asearch(("memories", user_id), limit=200)
    if not items:
        return "No memories saved yet."
    return "\n".join(f"- {item.value['fact']}" for item in items)


def get_tools() -> list:
    return [
        TavilySearchResults(max_results=5),
        calculator,
        search_linkedin_jobs,
        search_uploaded_documents,
        save_memory,
        list_memories,
    ]

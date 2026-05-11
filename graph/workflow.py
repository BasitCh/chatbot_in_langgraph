"""LangGraph workflow.

Shape:

    START -> chat_node -> [tools_condition]
                            |        |
                            v        v
                          tools    END
                            |
                            +--> chat_node  (loop until LLM stops calling tools)

`chat_node` does two things every turn:
  1. Pulls the user's long-term memories from the shared `BaseStore` and
     prepends them to the system prompt. The LLM sees them as background
     knowledge it can use without re-asking.
  2. Calls the LLM with the system prompt + the live conversation history.

The actual compilation (with checkpointer, store, and interrupt_before) is
done in app.py — this module just declares the shape.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.store.base import BaseStore

from graph.tools import get_tools

SYSTEM_PROMPT = """You are a helpful personal assistant with several tools.

UPLOADS — `search_uploaded_documents` returns chunks from PDFs, DOCX/TXT \
files, and images the user has uploaded in this conversation. Call it \
before answering whenever the user references uploads ("the document", \
"the PDF", "the image", "this file", filenames, etc.) OR the answer is \
likely inside their uploads. Ground your answer in the retrieved chunks \
and quote them when useful. If the chunks don't contain the answer, say \
so explicitly — don't guess.

LONG-TERM MEMORY — `save_memory` persists a single fact about the user \
across all future conversations. Use it proactively when the user shares \
durable information: their name, role, ongoing projects, preferences, \
goals. ONE fact per call. `list_memories` shows everything you have \
saved. Anything in your "What you already know about this user" block \
below is loaded from this same memory automatically each turn — you \
don't need to re-fetch it."""


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


_tools = get_tools()
_llm = ChatOpenAI(model="gpt-4o", streaming=True).bind_tools(_tools)


async def _chat_node(state: ChatState, config: RunnableConfig, *, store: BaseStore):
    # Pull every memory we have for this user. The store is keyed by
    # user_id (their Google email) so memories never leak across users.
    user_id = config["configurable"].get("user_id", "default")
    memories = await store.asearch(("memories", user_id), limit=200)

    system = SYSTEM_PROMPT
    if memories:
        bullets = "\n".join(f"- {m.value['fact']}" for m in memories)
        system = f"{SYSTEM_PROMPT}\n\nWhat you already know about this user:\n{bullets}"

    messages = [SystemMessage(content=system), *state["messages"]]
    response = await _llm.ainvoke(messages, config=config)
    return {"messages": [response]}


def build_workflow() -> StateGraph:
    workflow = StateGraph(ChatState)
    workflow.add_node("chat_node", _chat_node)
    workflow.add_node("tools", ToolNode(_tools))
    workflow.add_edge(START, "chat_node")
    workflow.add_conditional_edges("chat_node", tools_condition)
    workflow.add_edge("tools", "chat_node")
    return workflow


workflow = build_workflow()

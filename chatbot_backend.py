from typing import TypedDict, Annotated
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from chatbot_tools import ChatbotTools

load_dotenv()

# --- Graph State ---
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# --- Model & Tools ---
llm = ChatOpenAI(model="gpt-4o", streaming=True)
tools = ChatbotTools().getTools()
llm_with_tools = llm.bind_tools(tools)

# --- Node ---
async def chat_node(state: ChatState, config: RunnableConfig):
    # CRITICAL: config must be passed here for astream_events to work
    response = await llm_with_tools.ainvoke(state["messages"], config=config)
    return {"messages": [response]}

# --- Workflow Definition ---
workflow = StateGraph(ChatState)
workflow.add_node("chat_node", chat_node)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "chat_node")
workflow.add_conditional_edges("chat_node", tools_condition)
workflow.add_edge("tools", "chat_node")
from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from dotenv import load_dotenv
import sqlite3
import os
import streamlit as st

try:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
except Exception:
    load_dotenv()

llm = ChatOpenAI(model= 'gpt-4o')

class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def chat_node(state: ChatState):
    messages = state['messages']
    response = llm.invoke(messages)
    return {"messages": [response]}

#check pointer
conn = sqlite3.connect('chatbot_state.db', check_same_thread= False)
check_pointer = SqliteSaver(conn)

# --- Metadata (Titles) Functions ---
def init_db():
    """Initializes the metadata table for titles."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_metadata (
                thread_id TEXT PRIMARY KEY,
                title TEXT
            )
        """)

def save_single_title(thread_id: str, title: str):
    """Saves one specific title to the DB."""
    with conn:
        conn.execute("INSERT OR REPLACE INTO thread_metadata VALUES (?, ?)", (thread_id, title))

def fetch_all_titles():
    """Returns a dictionary of all {thread_id: title}."""
    cursor = conn.cursor()
    cursor.execute("SELECT thread_id, title FROM thread_metadata")
    return {row[0]: row[1] for row in cursor.fetchall()}

def retrieve_all_threads():
    """Returns a list of all thread IDs from LangGraph checkpoints."""
    all_threads = set()
    for checkpoint in check_pointer.list(None):
        all_threads.add(checkpoint.config['configurable']['thread_id'])
    return list(all_threads)

# --- Graph Construction ---
init_db()

graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")
graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer= check_pointer)

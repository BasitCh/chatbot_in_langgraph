import streamlit as st
import uuid
from langchain_core.messages import HumanMessage
from langgraph_backend import (
    chatbot, retrieve_all_threads, save_single_title, fetch_all_titles
)

# --- Utility Functions ---
def generate_thread_id():
    return str(uuid.uuid4())

def make_title(text: str) -> str:
    words = text.strip().split()
    title = ' '.join(words[:5])
    return title + "..." if len(words) > 5 else title

def load_conversation(thread_id: str):
    state = chatbot.get_state(config={'configurable': {'thread_id': thread_id}})
    messages = state.values.get('messages', [])
    ui_messages = []
    for m in messages:
        role = 'user' if isinstance(m, HumanMessage) else 'assistant'
        ui_messages.append({'role': role, 'content': m.content})
    return ui_messages

# --- Session State Initialization ---
if 'chat_threads' not in st.session_state:
    st.session_state['chat_threads'] = retrieve_all_threads()

if 'thread_titles' not in st.session_state:
    # Hydrate titles from the Database
    st.session_state['thread_titles'] = fetch_all_titles()

if 'thread_id' not in st.session_state:
    # Start with the last used thread or a brand new one
    if st.session_state['chat_threads']:
        st.session_state['thread_id'] = st.session_state['chat_threads'][-1]
    else:
        st.session_state['thread_id'] = generate_thread_id()

if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = load_conversation(st.session_state['thread_id'])

# --- Sidebar ---
st.sidebar.title("Conversations")
if st.sidebar.button("+ New Chat", use_container_width=True):
    new_id = generate_thread_id()
    st.session_state['thread_id'] = new_id
    st.session_state['chat_history'] = []
    # Note: We don't add it to chat_threads list until the first message is sent
    st.rerun()

st.sidebar.divider()

for t_id in st.session_state['chat_threads'][::-1]:
    title = st.session_state['thread_titles'].get(t_id, "New Conversation")
    is_active = (t_id == st.session_state['thread_id'])
    
    if st.sidebar.button(title, key=t_id, use_container_width=True, 
                         type='primary' if is_active else 'secondary'):
        st.session_state['thread_id'] = t_id
        st.session_state['chat_history'] = load_conversation(t_id)
        st.rerun()

# --- Main Chat ---
st.title("Basit AI ⚡")

for msg in st.session_state['chat_history']:
    with st.chat_message(msg['role']):
        st.markdown(msg['content'])

user_input = st.chat_input("Say something...")
if user_input:
    curr_id = st.session_state['thread_id']
    
    # 1. Handle Title Generation & Saving
    if curr_id not in st.session_state['thread_titles']:
        new_title = make_title(user_input)
        st.session_state['thread_titles'][curr_id] = new_title
        save_single_title(curr_id, new_title) # DATABASE SAVE (Single Row)
        
        if curr_id not in st.session_state['chat_threads']:
            st.session_state['chat_threads'].append(curr_id)

    # 2. Add to UI
    st.session_state['chat_history'].append({'role': 'user', 'content': user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # 3. Stream AI Response
    with st.chat_message("assistant"):
        def get_chunks():
            for chunk, _ in chatbot.stream(
                input={'messages': [HumanMessage(content=user_input)]},
                config={'configurable': {'thread_id': curr_id}},
                stream_mode='messages'
            ):
                yield chunk.content
        ai_msg = st.write_stream(get_chunks())
    
    st.session_state['chat_history'].append({'role': 'assistant', 'content': ai_msg})
    st.rerun()
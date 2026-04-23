#streamlit is stateless so we have to implement session state
import streamlit as st
from langchain_core.messages import HumanMessage
from langgraph_backend import chatbot
from dotenv import load_dotenv
import uuid


###### utility functions ########################
def generate_thread_id():
  return str(uuid.uuid4())

def add_thread(thread_id: str):
  if thread_id not in st.session_state['chat_threads']:
    st.session_state['chat_threads'].append(thread_id)

def reset_chat():
  st.session_state['chat_history'] = []
  thread_id = generate_thread_id()
  st.session_state['thread_id'] = thread_id

def load_conversation(thread_id: str):
  state = chatbot.get_state(config= {'configurable': {'thread_id': thread_id}})
  messages = state.values.get('messages', [])
  return messages

def make_title(text: str) -> str:
  words = text.strip().split()
  title = ' '.join(words[:5])
  if len(words) > 5:
    title += ' ...'
  return title
#################################################

load_dotenv()
st.set_page_config(page_title="Basit AI", page_icon="⚡", layout="centered")

###### session setp ########################
if 'thread_id' not in st.session_state:
  st.session_state['thread_id'] = generate_thread_id()

if 'chat_threads' not in st.session_state:
  st.session_state['chat_threads'] = []

if 'chat_history' not in st.session_state:
  st.session_state['chat_history'] = []

if ('thread_titles') not in st.session_state:
  st.session_state['thread_titles'] = {}

add_thread(st.session_state['thread_id'])

############################################


###### sidebar setup ##########################

if st.sidebar.button(label='Start New Chats'):
  reset_chat()
  st.rerun()

for thread_id in st.session_state['chat_threads'][::-1]:
  title = st.session_state['thread_titles'].get(thread_id, 'New Conversation')
  if st.sidebar.button(label= title, key= f"{thread_id}"):
    st.session_state['thread_id'] = thread_id
    messages = load_conversation(thread_id= thread_id)

    temp_messages = []
    for message in messages:
      if isinstance(message, HumanMessage):
        role = 'user'
      else:
        role = 'assistant'
      temp_msg = {'role': role, 'content': message.content}
      temp_messages.append(temp_msg)
    
    st.session_state['chat_history'] = temp_messages
    st.rerun()
##############################################

###### load conversation  ##########################

for message in st.session_state['chat_history']:
    with st.chat_message(message['role']):
      st.markdown(message['content'])  

##############################################

user_input = st.chat_input('Say something...')
if user_input:
  current_thread_id = st.session_state['thread_id']
  if current_thread_id not in st.session_state['thread_titles']:
    st.session_state['thread_titles'][current_thread_id] = make_title(text= user_input)

  # add human message to session state
  st.session_state['chat_history'].append({'role': 'user', 'content': user_input})
  with st.chat_message('user'):
    st.markdown(user_input)
  
  with st.chat_message('assistant'):
    def get_chunks():
      for chunk, metadata in chatbot.stream(
        input= {'messages': [HumanMessage(content= user_input)]},
        config= {'configurable': {'thread_id': current_thread_id}},
        stream_mode= 'messages'
      ):
        yield chunk.content
      
    ai_message = st.write_stream(get_chunks())
    
  st.session_state['chat_history'].append({'role': 'assistant', 'content': ai_message})
  st.rerun()
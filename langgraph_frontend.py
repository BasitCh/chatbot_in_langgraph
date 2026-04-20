#streamlit is stateless so we have to implement session state
import streamlit as st
from langchain_core.messages import HumanMessage
from langgraph_backend import chatbot

CONFIG = {'configurable': {'thread_id': 'thread-1'}}

#if there is nothing in session state then load with empty array
if 'chat_history' not in st.session_state:
  st.session_state['chat_history'] = []

for message in st.session_state['chat_history']:
    with st.chat_message(message['role']):
      st.markdown(message['content'])  


user_input = st.chat_input('Say something...')
if user_input:
  # add human message to session state
  st.session_state['chat_history'].append({'role': 'user', 'content': user_input})
  with st.chat_message('user'):
    st.markdown(user_input)
  
  response = chatbot.invoke({'messages': [HumanMessage(content= user_input)]}, config= CONFIG)
  ai_message = response['messages'][-1].content
  # add ai message to session state
  st.session_state['chat_history'].append({'role': 'assistant', 'content': ai_message})
  
  with st.chat_message('assistant'):
    st.markdown(ai_message)

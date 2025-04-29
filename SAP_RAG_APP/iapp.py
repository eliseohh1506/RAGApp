import streamlit as st 
import functions as func


#function to chat
@st.experimental_fragment
def init_chat():
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    if all_doc == True:
        # st.write('exe')
        response = func.call_chat_api(prompt)
    else:
        response = func.call_chat_api(prompt, st.session_state.file_name)
    ans = func.get_source(response)
    with st.chat_message("assistant"):
        st.markdown(ans)
    st.session_state.messages.append({"role": "assistant", "content": ans})


# set page config
st.set_page_config(
    page_title="Chat-Bot",
    page_icon="🤖",
    layout="wide",
)


# declare session state variables to store chat history 
if "messages" not in st.session_state:
    st.session_state.messages = []


#set chat with all data and initiate chat
all_doc = True

#load chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Come on lets Chat!"):
    if prompt.lower() == "clear chat":
        st.session_state.messages = []

    else:
        init_chat()


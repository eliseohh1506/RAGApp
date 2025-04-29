import streamlit as st 
import functions as func
import os


#function to clear the local chat history
@st.experimental_fragment
def clear_chat():
    st.session_state.messages = []

#function to chat with docs
@st.experimental_fragment
def init_chat():

    #write and save user prompt
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    #check if chat with all docs or a selected doc
    if all_doc == True:
        # st.write('exe')
        response = func.call_chat_api(prompt)
    else:
        response = func.call_chat_api(prompt, st.session_state.file_name)

    #write and save assistant response
    with st.chat_message("assistant"):
        st.write(response['answer'])
    st.session_state.messages.append({"role": "assistant", "content": response['answer']})


#function to get list of uploaded docs from db
@st.experimental_fragment
def get_uploaded_docs():
    conn = func.get_hana_db_conn()
    df = func.get_sap_table('MAV_SAP_RAG', 'DBADMIN', conn)
    if df.shape[0] != 0:
        doc_list = [eval(d).get("source") for d in df['VEC_META']]
        df['file_name'] = [os.path.basename(path) for path in doc_list]
        doc_list = df['file_name'].unique()
        return doc_list
    else: 
        return []


#fuction to clear data of selected or all docs from hana DB
@st.experimental_dialog("Are you sure?")
def clear_data_db(file = None):
    c1, c2 = st.columns(2)
    # st.write("Are you sure?")
    with c1:
        if st.button("Clear Data"):
            if file == None:
                mess = func.delete_table(None)
            else:
                mess = func.delete_table(file)
            st.rerun()
            return mess
    

#set page config
st.set_page_config(
    page_title="Chat-Bot",
    page_icon="🤖",
    layout="wide",
)

#declare session state variables to store chat history and file name
if "messages" not in st.session_state:
    st.session_state.messages = []
if "file_name" not in st.session_state:
    st.session_state.file_name = ""

 

st.title("Chat with Data")

st.sidebar.header("File Manager")

#button to clear the local chat history
if st.sidebar.button("Clear Chat"):
    clear_chat()   


# Dropdown to select if chat with pre-uploaded docs or file upload
chat_mode = st.sidebar.selectbox("How do you want to start the chat?", ( "Chat with Pre-Uploaded Data","File Upload"))


#if chat by upploading a file
if chat_mode == "File Upload":

    #upload fileof type csv, txt, pdf
    file = st.sidebar.file_uploader("Upload a file to Chat with", type=["csv", "txt", "pdf"])
    doc_list = get_uploaded_docs()

    # if file is already exist in db then show message, if not then call the funciton to upload the file into db by vectorize it.
    if file is not None:

        if file.name not in doc_list:
            api_output = func.call_file_api(file)
            st.sidebar.write(api_output["status"])
            st.session_state.file_name = api_output["file_name"]
            if api_output["status"] == "Success":
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                if prompt := st.chat_input("Come on lets Chat!"):
                    init_chat()
        else:
            if file.name in doc_list:
                st.sidebar.write("File Name already Exist")


# if chat with pre-uploaded docs
elif chat_mode == "Chat with Pre-Uploaded Data":
    doc_list = get_uploaded_docs() #get list of uploaded docs from db
    all_doc = st.sidebar.toggle("All Documents", ) #check if chat with all docs or a selected doc
    # if not all docs then select doc from sidebar
    if all_doc == False: 
        file_name = st.sidebar.selectbox("Select Document", doc_list)
        st.session_state.file_name = file_name

    #load chat history from local history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    

    # if prompt is not empty then call the function to get response
    if prompt := st.chat_input("Come on lets Chat!"):
        init_chat()
        print(st.session_state.messages)


    #clear data from db based on selection by clicking button
    if clear_data := st.sidebar.button("Clear Data from DB", key="clear_data"):
        if all_doc:
            clear_data_db()
        else:
            clear_data_db(file_name)
    



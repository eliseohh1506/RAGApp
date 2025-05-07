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

    response = func.call_chat_api(prompt, st.session_state.policy_doc)

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
        # print("doclist: ", doc_list)
        df['file_name'] = [os.path.basename(path) for path in doc_list]
        doc_list = df['file_name'].unique()
        return doc_list
    else: 
        return []

@st.experimental_fragment
def get_dox_documents():
    #Connect to DOX
    func.connect_dox_api()
    results = func.dox_get_all_documents()
    if results and isinstance(results, list):
        doc_list = [os.path.basename(doc["fileName"]) for doc in results if "fileName" in doc]
        doc_list = list(set(doc_list))  # optional: remove duplicates
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
if "policy_doc" not in st.session_state:
    st.session_state.policy_doc = ""
if "invoice" not in st.session_state:
    st.session_state.invoice = {}

 

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
    fileContract = st.sidebar.file_uploader("Upload a Contract/Policy file", type=["csv", "txt", "pdf"])
    #TO DO handle upload to DOX API
    fileInvoice = st.sidebar.file_uploader("Upload an Invoice for Compliance Check", type=["csv", "txt", "pdf"])
    doc_list = get_uploaded_docs()
    invoice_list = get_dox_documents()

    # if file is already exist in db then show message, if not then call the funciton to upload the file into db by vectorize it.
    if fileContract is not None:

        if fileContract.name not in doc_list:
            api_output = func.call_file_api(fileContract)
            st.sidebar.write(api_output["status"])
            st.session_state.file_name = api_output["file_name"]
            if api_output["status"] == "Success":
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                if prompt := st.chat_input("Come on lets Chat!"):
                    init_chat()
        else:
            if fileContract.name in doc_list:
                st.sidebar.write("File Name already Exist")

    # if fileInvoice is not None:
    #     if fileContract.name not in invoice_list:
    #         api_output = 

# if chat with pre-uploaded docs
elif chat_mode == "Chat with Pre-Uploaded Data":
    doc_list = get_uploaded_docs() #get list of uploaded docs from db
    invoice_list = get_dox_documents()
    policy_doc = st.sidebar.selectbox("Select Policy Document", doc_list)
    st.session_state.policy_doc = policy_doc
    # all_invoice = st.sidebar.toggle("All Documents", ) #check if chat with all docs or a selected doc
    # if not all docs then select doc from sidebar
    invoice = st.sidebar.selectbox("Select Document to check for compliance", invoice_list)
    st.session_state.invoice = func.dox_get_fields(invoice)

    #load chat history from local history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    

    # if prompt is not empty then call the function to get response
    if prompt := st.chat_input("Come on lets Chat!"):
        init_chat()
        print(st.session_state.messages)


    #clear data from db based on selection by clicking button
    if clear_data := st.sidebar.button("Clear Policy Documents from DB", key="clear_data"):
        clear_data_db(policy_doc)
    



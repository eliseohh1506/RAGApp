import streamlit as st 
import functions as func
import os
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv
load_dotenv()

os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"] = os.environ.get("AWS_DEFAULT_REGION")
bucket_name = os.environ.get("AWS_BUCKET_NAME")
s3 = boto3.client("s3")

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

    response = func.call_chat_api(prompt, st.session_state.policy_doc, st.session_state.invoice)
    #write and save assistant response
    with st.chat_message("assistant"):
        st.write("**Context Used for Answering:**")
        st.markdown(response["context"])
        # Display the final answer
        st.write("**Answer:**")
        st.markdown(response["answer"])
    st.session_state.messages.append({"role": "assistant", "content": response["answer"]})


#function to get list of uploaded docs from AWS S3 bucket 
@st.experimental_fragment
def get_uploaded_docs():
    bucket_name = os.environ.get("AWS_BUCKET_NAME")
    response = s3.list_objects(Bucket=bucket_name)

    # Safely get list of objects or empty list if none exist
    contents = response.get('Contents', [])
    extracted_titles = [doc['Key'] for doc in contents]

    return extracted_titles

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
    
@st.experimental_fragment
def get_dox_document_type():
    func.connect_dox_api()
    results = func.dox_get_schemas()
    unique_document_types = sorted({schema.get("documentType") for schema in results})
    return unique_document_types

@st.experimental_fragment
def get_dox_schema(document_type):
    func.connect_dox_api()
    results = func.dox_get_schemas()
    matching_schemas = [
        schema.get("name")
        for schema in results
        if schema.get("state") == "active" and schema.get("documentType") == document_type
    ]
    return sorted(matching_schemas)

@st.experimental_fragment
def generate_presigned_url(object_key, expiration=3600):
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": object_key},
        ExpiresIn=expiration
    )

@st.experimental_fragment
def dox_url(invoiceId):
    return f"{os.environ.get('DOX_UI_URL')}clientId={os.environ.get('DOX_CLIENT_NAME')}#/invoiceviewer&/iv/detailDetail/{invoiceId}/TwoColumnsBeginExpanded"

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
                s3.delete_objects(Bucket=bucket_name, Delete={"Objects":[
                    {'Key': file}
                ]})
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
chat_mode = st.sidebar.selectbox("How do you want to start the chat?", ( "Chat","File Upload"))


#if chat by upploading a file
if chat_mode == "File Upload":

    #upload fileof type csv, txt, pdf
    fileContract = st.sidebar.file_uploader("Upload a PDF Documentation", type=[ "pdf"])

    url_input = st.sidebar.text_input(label="Key in URL of documentation")

    # Confirm button
    if st.sidebar.button("Confirm URL"):
        st.session_state['confirmed_url'] = url_input

    # Access the confirmed URL
    doc_url = st.session_state.get('confirmed_url')
    # get all links associated with given url and crawl it, save it to HANA DB as well as S3
    if doc_url is not None:
        func.web_crawl(doc_url)

    doc_list = get_uploaded_docs()

    # if file is already exist in db then show message, if not then call the funciton to upload the file into db by vectorize it.
    if fileContract is not None:
        if fileContract.name not in doc_list:
            #Upload to both S3 and Hana vector store
            bucket_name=os.environ.get("AWS_BUCKET_NAME")
            try:
                api_output = func.call_file_api(fileContract)
                fileContract.seek(0)
                st.sidebar.write(api_output["status"])
                s3.upload_fileobj(fileContract, bucket_name, fileContract.name)
                #Update metadata after upload
                s3.copy_object(
                    Bucket=bucket_name,
                    CopySource={'Bucket': bucket_name, 'Key': fileContract.name},
                    Key=fileContract.name,
                    MetadataDirective='REPLACE',
                    ContentDisposition='inline',
                    ContentType='application/pdf'
                )
                st.session_state.file_name = api_output["file_name"]
                if api_output["status"] == "Success":
                    for message in st.session_state.messages:
                        with st.chat_message(message["role"]):
                            st.markdown(message["content"])
                    if prompt := st.chat_input("Come on lets Chat!"):
                        init_chat()
            except FileNotFoundError:
                st.sidebar.write(f"Error: File '{fileContract.name}' not found.")
            except NoCredentialsError:
                st.sidebar.write("Error: No AWS credentials found.")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                st.sidebar.write(f"Error: {error_code} - {e}")
            except Exception as e:
                st.sidebar.write(f"An unexpected error occurred: {e}")
        else:
            if fileContract.name in doc_list:
                st.sidebar.write("File Name already Exist")
    
    #load chat history from local history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    

    # if prompt is not empty then call the function to get response
    if prompt := st.chat_input("Come on lets Chat!"):
        init_chat()
        print(st.session_state.messages)


# if chat with pre-uploaded docs
elif chat_mode == "Chat":
    doc_list = get_uploaded_docs() #get list of uploaded docs from db
    # Sidebar dropdown shows only titles
    if not doc_list:
        doc_list = ["No PDF documentations grounded"]
    policy_doc = st.sidebar.selectbox("Select PDF Documentation", doc_list)

    if policy_doc != "No documents available":
        doc_url = generate_presigned_url(policy_doc)
        st.sidebar.markdown(
            f"""
            <a href="{doc_url}" target="_blank">
                <button style="background-color:#FFFFFF;color:black;padding:10px 16px;border:none;border-radius:10px;cursor:pointer;margin-bottom: 20px">
                    See Policy Document
                </button>
            </a>
            """,
            unsafe_allow_html=True
        )
        if clear_data := st.sidebar.button("Clear PDF Documentations from DB", key="clear_data"):
            clear_data_db(policy_doc)
    else:
        st.sidebar.info("Please upload a PDF documentation to begin.")


    st.session_state.policy_doc = policy_doc
   
    #load chat history from local history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    

    # if prompt is not empty then call the function to get response
    if prompt := st.chat_input("Come on lets Chat!"):
        init_chat()
        print(st.session_state.messages)

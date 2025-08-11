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
        # st.write("**Context Used for Answering:**")
        # st.markdown(response["context"])
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
    st.write("Are you sure?")
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


st.sidebar.header("File Manager")

#button to clear the local chat history
if st.sidebar.button("Clear Chat"):
    clear_chat()   


# Dropdown to select if chat with pre-uploaded docs or file upload
chat_mode = st.sidebar.selectbox("How do you want to start the chat?", ( "Chat with Pre-Uploaded Data","File Upload"))


#if chat by uploading a file
if chat_mode == "File Upload":

    st.title("Upload Files")
    #upload fileof type csv, txt, pdf
    fileContract = st.sidebar.file_uploader("Upload a Contract/Policy file", type=[ "pdf"])
    fileInvoice = st.sidebar.file_uploader("Upload an Invoice for Compliance Check", type=["jpeg", "png", "pdf"])
    dox_doc_type = st.sidebar.selectbox("Select Document Type", (get_dox_document_type()))
    dox_schema = st.sidebar.selectbox("Select Schema", (get_dox_schema(dox_doc_type)))
    
    def handle_invoice_upload():
        file = fileInvoice
        doc_type = dox_doc_type
        schema = dox_schema

        if file:
            invoice_list = get_dox_documents()
            if file.name not in invoice_list:
                api_output = func.dox_upload_file(file, doc_type, schema)
                st.session_state.file_name = api_output.get("file_name")
                if api_output.get("status") == "PENDING":
                    st.session_state.upload_msg = "File is being processed"
                    for message in st.session_state.get("messages", []):
                        with st.chat_message(message["role"]):
                            st.markdown(message["content"])
                    if prompt := st.chat_input("Come on lets Chat!"):
                        init_chat()
                else:
                    st.session_state.upload_msg = "Upload Failed"
            else:
                st.session_state.upload_msg = "File Name already Exist"
        else:
            st.session_state.upload_msg = "No file selected"

    # TO DO - add a button to upload the file to DOX
    st.sidebar.button("Upload Invoice Document", key="upload_doc", on_click=handle_invoice_upload)
    
    if "upload_msg" in st.session_state:
        st.sidebar.write(st.session_state.upload_msg)
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

# if chat with pre-uploaded docs
elif chat_mode == "Chat with Pre-Uploaded Data":
    st.title("Compliance Check Chat")
    doc_list = get_uploaded_docs() #get list of uploaded docs from db
    invoice_list = get_dox_documents()
    # Sidebar dropdown shows only titles
    if not doc_list:
        doc_list = ["No documents available"]
    policy_doc = st.sidebar.selectbox("Select Policy Document", doc_list)

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
        if clear_data := st.sidebar.button("Clear Policy Documents from DB", key="clear_data"):
            clear_data_db(policy_doc)
    else:
        st.sidebar.info("Please upload a policy document to begin.")


    st.session_state.policy_doc = policy_doc
    # if not all docs then select doc from sidebar
    if invoice_list:  # only show invoice-related UI if list is not empty
        invoice = st.sidebar.selectbox("Select Document to check for compliance", invoice_list)
        invoiceId = func.dox_getId(invoice)
        st.session_state.invoice = func.dox_get_fields(invoice)

        url = dox_url(invoiceId)

        st.sidebar.markdown(
            f"""
            <a href="{url}" target="_blank">
                <button style="background-color:#FFFFFF;color:black;padding:10px 16px;border:none;border-radius:10px;cursor:pointer;margin-bottom: 20px">
                    Check Invoice Extracted Fields
                </button>
            </a>
            """,
            unsafe_allow_html=True
        )
    else:
        st.sidebar.selectbox("Select Document to check for compliance", ["No documents available"], disabled=True)
        st.sidebar.markdown(
            """
            <button style="background-color:#CCCCCC;color:black;padding:10px 16px;border:none;border-radius:10px;cursor:not-allowed;margin-bottom: 20px" disabled>
                📄 Check Invoice Extracted Fields
            </button>
            """,
            unsafe_allow_html=True
        )
    #load chat history from local history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    

    # if prompt is not empty then call the function to get response
    if prompt := st.chat_input("Come on lets Chat!"):
        init_chat()
        print(st.session_state.messages)

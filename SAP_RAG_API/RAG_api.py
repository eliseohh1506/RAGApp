from fastapi import FastAPI, File, UploadFile, Form
import os
import api_functions as func
from langchain_community.vectorstores.hanavector import HanaDB
# from langchain_huggingface import HuggingFaceEndpoint
from langchain_community.chat_message_histories import ChatMessageHistory
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
# OpenAIEmbeddings to create text embeddings
from gen_ai_hub.proxy.langchain.openai import OpenAIEmbeddings
from gen_ai_hub.proxy import get_proxy_client
from gen_ai_hub.orchestration.models.template import TemplateValue
from gen_ai_hub.orchestration.models.llm import LLM
from gen_ai_hub.orchestration.service import OrchestrationService
from dotenv import load_dotenv

load_dotenv()

#initiate fastapi as app
app = FastAPI()

os.environ["AICORE_AUTH_URL"] = os.environ.get("AICORE_AUTH_URL")
os.environ["AICORE_CLIENT_ID"] = os.environ.get("AICORE_CLIENT_ID")
os.environ["AICORE_CLIENT_SECRET"] = os.environ.get("AICORE_CLIENT_SECRET")
os.environ["AICORE_BASE_URL"] = os.environ.get("AICORE_BASE_URL")
os.environ["AICORE_RESOURCE_GROUP"]= os.environ.get("AICORE_RESOURCE_GROUP")

#Set up orchestration service 
aicore_client = get_proxy_client().ai_core_client
orchestration_service = OrchestrationService(api_url=os.environ.get("ORCHESTRATION_URL"))
#create hanaDB connection and embeddings
conn = func.get_hana_db_conn()
embeddings = OpenAIEmbeddings(deployment_id=os.environ.get("EMBEDDING_DEPLOYMENT_ID"))
history = ChatMessageHistory()

@app.get("/embedding-dim")
async def check_embedding_dim():
    test_sentence = "This is a test sentence."
    vectors = embeddings.embed_documents([test_sentence])
    
    if not vectors:
        return {"error": "No embeddings returned"}
    
    vector_length = len(vectors[0])
    return {"embedding_dimension": vector_length}


#endpoint to process uploaded file
@app.post("/upload")
async def process_input(file: UploadFile = File(...)): #get file

    #store file temporarily
    file_path = func.get_temp_file_path(file)
    file_extension = os.path.splitext(file_path)[1]
    #create vector connection
    db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")
    #find format of file, process it accourding to it and store it as vectors in hanaDB
    texts = []

    if file_extension == ".pdf":
        texts = func.get_text_from_pdf(file_path)
    elif file_extension == ".txt":
        texts = func.get_text_from_txt(file_path)
    elif file_extension == ".csv":
        texts = func.get_text_from_csv(file_path)
    else:
        return {"status": "File type not supported"}

    print(f"Extracted {len(texts)} chunks from file {file.filename}")

    if not texts or all(doc.page_content.strip() == "" for doc in texts):
        return {"status": "File uploaded, but contains no readable content"}

    db.add_documents(texts)
    return {"status": "Success", "file_name": file.filename}



#endpoint to process query and return answer
@app.post("/chat")
async def process_input(query: str = Form(...), file_name: str = Form("Temp"), invoiceDetails: str = Form({})): #get query and file name

    id = os.environ.get("LLM_DEPLOYMENT_ID")
    llm = ChatOpenAI(deployment_id=id)

    #create vector connection
    db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")

    #create QA chain
    qa_chain = func.get_llm_chain(llm, db, file_name, invoiceDetails)

    question_with_invoice = {
        "question": query,
        "chat_history": history,
        "invoiceDetails": invoiceDetails
    }
    #get answer
    result = qa_chain.invoke(question_with_invoice)
    return result


#endpoint to clear data
@app.post("/clear_data")
async def clear_data(filter: str = Form("None")): # get filter file name

    #if there is no file name delete all docs in table
    if filter == "None":
        db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")
        db.delete(filter={})
        return {"status": "Success"}
    
    #else delete all docs with that file name in metadata
    else:
        db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")
        db.delete(filter={"source":{"$like": "%"+filter+"%"}})
        return {"status": "Success"}

 

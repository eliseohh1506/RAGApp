from fastapi import FastAPI, File, UploadFile, Form
from huggingface_hub import HfApi
import os
import api_functions as func
from langchain_community.vectorstores.hanavector import HanaDB
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_huggingface import HuggingFaceEndpoint
from langchain.memory import ChatMessageHistory
from dotenv import load_dotenv

load_dotenv()

#initiate fastapi as app
app = FastAPI()

#get HuggingFace token and login to HuggingFace
HF_key = os.environ.get("HF_TOKEN")
HFapi = HfApi(HF_key)

#create hanaDB connection and embeddings
conn = func.get_hana_db_conn()
embeddings = HuggingFaceInferenceAPIEmbeddings(
    api_key=HF_key, model_name="sentence-transformers/all-MiniLM-L6-v2"
)
history = ChatMessageHistory()

@app.get("/embedding-dim")
async def check_embedding_dim():
    test_sentence = "This is a test sentence."
    vectors = embeddings.embed_documents([test_sentence])
    
    if not vectors:
        return {"error": "No embeddings returned"}
    
    vector_length = len(vectors[0])
    print(vectors)
    return {"embedding_dimension": vector_length}


#endpoint to process uploaded file
@app.post("/upload")
async def process_input(file: UploadFile = File(...)): #get file

    #store file temporarily
    file_path = func.get_temp_file_path(file)
    file_extension = os.path.splitext(file_path)[1]
    #create vector connection
    db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")
    error = 0
    #find format of file, process it accourding to it and store it as vectors in hanaDB
    if file_extension == ".pdf":
        db.add_documents(func.get_text_from_pdf(file_path))
    elif file_extension == ".txt":
        db.add_documents(func.get_text_from_txt(file_path))
    elif file_extension == ".csv":
        db.add_documents(func.get_text_from_csv(file_path))
    else:
        error = 1
    
    if error == 0:
        return {"status": "Success", "file_name": file.filename}
    else:
        return {"status": "File type not supported"}



#endpoint to process query and return answer
@app.post("/chat")
async def process_input(query: str = Form(...), file_name: str = Form("Temp")): #get query and file name

    #create llm 
    llm = HuggingFaceEndpoint(
        repo_id="mistralai/Mistral-7B-Instruct-v0.3",
        task="text-generation",
        max_new_tokens=512,
        do_sample=False,
        repetition_penalty=1.03,
    )

    #create vector connection
    db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")

    #create QA chain
    qa_chain = func.get_llm_chain(llm, db, file_name)

    #get answer
    result = qa_chain.invoke({"question": query, "chat_history": []})

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

 

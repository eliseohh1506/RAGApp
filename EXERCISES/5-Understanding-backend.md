# Understanding Backend

In this section, we will be breaking down the backend into bite sized code snippets and explain each snippet's functionality. Refer to ``SAP_RAG_API/RAG_api.py`` for full backend code. Refer to ``README.md`` to set up application on your local computer. 

This snippet are the libraries needed in the RAG_api.py file. LLM used to convert text to embeddings will be the OpenAI embedding model deployed in SAP AI Launchpad in Exercise 2.
```
from fastapi import FastAPI, File, UploadFile, Form
import os
import api_functions as func
from langchain_community.vectorstores.hanavector import HanaDB
from langchain_community.chat_message_histories import ChatMessageHistory
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
from gen_ai_hub.proxy.langchain.openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

#initiate fastapi as app
app = FastAPI()

conn = func.get_hana_db_conn()
embeddings = OpenAIEmbeddings(deployment_id=os.environ.get("EMBEDDING_DEPLOYMENT_ID"))
history = ChatMessageHistory()
```

## 1: "/upload" API Endpoint

This snippet details the ``/upload`` API end point implementation that we will call in [call_file_api() function](https://github.com/eliseohh1506/RAGApp/blob/main/EXERCISES/3-Understanding-frontendpt1.md#2-upload-file-page--upload-policy-functionality) 

> ### Prerequisite - Set up HANA DB Table correctly

Ensure that you create a new table named "MAV_SAP_RAG". Within this table, you should have 3 columns with the respective COLUMN_NAME, DATA_TYPE_NAME and LENGTH seen below.
![Table metadata](assets/HANA_table.png)
> Note that vector length might defer based on the embedding llm model's dimentions produced. OpenAI's text-embedding-3-small model produces 1536 dimensions hence the length. 

In the following function, we first connect to the HanaDB through the langchain hana vector SDK. If the file is in PDF, ``get_text_from_pdf`` function in ``api_functions.py`` is called and a list of the formatted text documents is returned. Currently, this app only supports uploading of PDF files but you can easily extend the file types by creating more functions similar to ``get_text_from_pdf()``. 

If there is documents extracted, ``db.add_documents(texts)`` will convert the document's text into embeddings, and the respective vector embeddings, metadata and the raw text is saved into the HANA DB table. 
```
@app.post("/upload")
async def process_input(file: UploadFile = File(...)): #get file

    #store file temporarily
    file_path = func.get_temp_file_path(file)
    file_extension = os.path.splitext(file_path)[1]
    #create vector connection
    db = HanaDB(embedding=embeddings, connection=conn, table_name="MAV_SAP_RAG")
    texts = []

    if file_extension == ".pdf":
        texts = func.get_text_from_pdf(file_path)
    else:
        return {"status": "File type not supported"}

    print(f"Extracted {len(texts)} chunks from file {file.filename}")

    if not texts or all(doc.page_content.strip() == "" for doc in texts):
        return {"status": "File uploaded, but contains no readable content"}

    db.add_documents(texts)
    return {"status": "Success", "file_name": file.filename}
```

The following function first opens up the PDF, extract the text, formats the text into a Document with the necessary metadata and proceeds to split the documents into chunks with the ``RecursiveCharacterTextSplitter`` while preserving the metadata. In the event that the PDF has images where text is unabled to be extracted by the ``pdfplumer`` library, we will use ``pytesseract``, which is an open source OCR python library to extract the text out of the images. 
```
def get_text_from_pdf(file_path):
    texts = []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text or text.strip() == "":
                # OCR fallback if no text found
                image = page.to_image(resolution=300).original
                text = pytesseract.image_to_string(image)

            # Create a document with metadata
            doc = Document(id=os.path.basename(file_path), 
                           page_content=text, 
                           metadata={"page": i + 1, 
                                     "title": os.path.basename(file_path)})

            # Chunk this single page-document while preserving metadata
            chunks = text_splitter.split_documents([doc])
            texts.extend(chunks)

    return texts
```

## 2: "/chat" API Endpoint
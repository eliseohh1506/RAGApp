import pandas as pd
import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
import tempfile
from langchain_core.prompts import PromptTemplate
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from hdbcli import dbapi
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.docstore.document import Document
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import re
from dotenv import load_dotenv
from langchain.schema import Document
import pdfplumber
from PIL import Image
import pytesseract

load_dotenv()


#function to get hanaDB connection
def get_hana_db_conn():
    conn = dbapi.connect(
            address=os.environ.get("Hostname"),
            port=os.environ.get("Port"),
            user=os.environ.get("HANA_USERNAME"),
            password=os.environ.get("Password"),
    )
    return conn

#function to store file in temp dir and send temp file path
def get_temp_file_path(file):
    temp_dir = tempfile.mkdtemp()
    # Save the uploaded PDF to the temporary directory
    path = os.path.join(temp_dir, file.filename)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return path

#function to process pdf, convert it as docs and return pages
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
            doc = Document(page_content=text, metadata={"page": i + 1, "source": file_path, "filename": os.path.basename(file_path)})

            # Chunk this single page-document while preserving metadata
            chunks = text_splitter.split_documents([doc])
            texts.extend(chunks)

    return texts

#function to process csv, convert it as docs and return pages
def get_text_from_csv(file, key_column):
    texts = []
    df = pd.read_csv(file)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    for i, row in df.iterrows():
        content = str(row[key_column])
        metadata = {
            "row": i + 1,
            "source": file,
            "filename": os.path.basename(file)
        }
        doc = Document(page_content=content, metadata=metadata)
        chunks = text_splitter.split_documents([doc])
        texts.extend(chunks)

    return texts

#function to process txt, convert it as docs and return pages
def get_text_from_txt(file):
    texts = []
    loader = TextLoader(file)
    text_documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    for i, doc in enumerate(text_documents):
        chunks = text_splitter.split_documents([doc])
        for chunk in chunks:
            chunk.metadata.update({
                "page": i + 1,
                "source": file,
                "filename": os.path.basename(file)
            })
        texts.extend(chunks)

    return texts

#function to create llm-chain and return it
#TO DO - incorporate details from DOX to cross check with policy documents. 
def get_llm_chain(llm, db, file_name, invoiceDetails):

    # set the prompt templte
    prompt_template = """
    You are a compliance assistant. Based on the extracted invoice fields and the policy document context, answer the user question.

    ### Extracted Invoice Fields:
    {invoiceDetails}
    
    ### Policy Document Context:
    {context}

    ### User Question:
    {question}

    Rules:
    - Answer question directly and concised
    - If no compliance check implied by user question, don't do compliance check
    - Be concise and explain which fields are compliant or non-compliant if asked to compare extracted fields against policy document.
    - Include the **file name** and **page number** for each policy rule you refer to. If unknown, write 'Unknown'.
    """
    PROMPT = PromptTemplate(
        template=prompt_template,
        input_variables=["question", "invoiceDetails"]
    )

    # Use ConversationalRetrievalChain manually constructed
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        input_key="question",
        output_key="answer",
        return_messages=True
    )

    retriever = db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": 5,
            "score_threshold": 0.3,
            "filter": {"source": {"$like": "%" + file_name + "%"}}
        }
    )

    # Create the chain that integrates memory, retriever, and the prompt
    qa_chain = ConversationalRetrievalChain.from_llm(
        llm,
        retriever,
        memory=memory,
        return_source_documents=True,
        combine_docs_chain_kwargs={
            "prompt": PROMPT,
            "document_variable_name": "context"
        }
    )

    return qa_chain

#function to extract answer from string
def extract_between_colon_and_period(input_string):
    try:
        start_index = input_string.index('Answer:') + len('Answer:')
        if '.' in input_string[start_index:]:
            end_index = input_string[start_index:].index('.')
            extracted_substring = input_string[start_index:][:end_index].strip() + '.'
        else:
            extracted_substring = input_string[start_index:].strip()
        return extracted_substring
    except ValueError:
        return None
    

#function to convert cid to char to decode the encoded pdf pages
def cidToChar(cidx):
    return chr(int(re.findall(r'\/g(\d+)',cidx)[0]) + 29)


#function to decode the encoded pdf pages
def decode(sentence):
  sen = ''
  for x in sentence.split('\n'):
    if x != '' and x != '/g3':         # merely to compact the output
      abc = re.findall(r'\/g\d+',x)
      if len(abc) > 0:
          for cid in abc: x=x.replace(cid, cidToChar(cid))
      sen += repr(x).strip("'")

  return re.sub(r'\s+', ' ', sen)
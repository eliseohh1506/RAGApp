import pandas as pd
import os
from langchain_community.document_loaders import TextLoader
import tempfile
from hdbcli import dbapi
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.docstore.document import Document
from langchain_community.document_loaders import TextLoader
from langchain.document_loaders import WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langgraph.graph import START, StateGraph
from typing_extensions import List, TypedDict
import re
from dotenv import load_dotenv
from langchain.schema import Document
import pdfplumber
from typing import AsyncGenerator
from PIL import Image
import pytesseract
import requests
import bs4
import boto3
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

load_dotenv()
os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID")
os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY")
os.environ["AWS_DEFAULT_REGION"] = os.environ.get("AWS_DEFAULT_REGION")
bucket_name = os.environ.get("AWS_BUCKET_NAME")
s3 = boto3.client("s3")

# Format documents to include source references in the context
def format_documents_with_metadata(docs):
    return "\n\n".join(
        f"[Source: {doc.metadata.get('filename', 'Unknown')}, Page: {doc.metadata.get('page', 'Unknown')}]\n{doc.page_content}"
        for doc in docs
    )

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
            doc = Document(id=os.path.basename(file_path), 
                           page_content=text, 
                           metadata={"page": i + 1, 
                                     "source": os.path.basename(file_path)})

            # Chunk this single page-document while preserving metadata
            chunks = text_splitter.split_documents([doc])
            texts.extend(chunks)

    return texts

#function to process web page links, convert to Docs and chunk it, saving it to S3 
def get_text_from_links(links):
    texts = []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )
    for url in links:
        print(f"Processing {url} ...")
        # Load webpage content with filtering classes if needed
        loader = WebBaseLoader(
            web_paths=[url],
            bs_kwargs=dict(
                parse_only=bs4.SoupStrainer("main", class_="main")
            ),
        )
        docs = loader.load()
        print(docs)
        for doc in docs:
            # Optional: parse the URL to get a simple filename-like ID
            parsed_url = urlparse(url)
            file_id = os.path.basename(parsed_url.path) or parsed_url.netloc

            # Create a new Document with id and cleaned metadata
            new_doc = Document(
                page_content=doc.page_content,
                metadata={
                    "id": file_id,
                    "source": url,
                }
            )

            # Chunk this one document
            chunks = text_splitter.split_documents([new_doc])
            texts.extend(chunks)
        
    return texts

# Crawl all links on given page
def get_all_links(base_url):
    response = requests.get(base_url)
    soup = BeautifulSoup(response.text, "html.parser")
    links = set()

    parsed_base = urlparse(base_url)
    base_netloc = parsed_base.netloc
    base_path = parsed_base.path.rstrip("/")

    for tag in soup.find_all("a", href=True):
        href = tag['href']
        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)

        # Same domain
        if parsed_url.netloc != base_netloc:
            continue

        # Only include links nested under base path
        target_path = parsed_url.path.rstrip("/")
        if target_path.startswith(base_path) and target_path != base_path:
            links.add(full_url)

    return [base_url] + sorted(links)

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
def get_llm_chain(llm, db, invoiceDetails):

    # set the prompt templte
    prompt_template = """
    You are tasked to convert SAP CSN structures into SQL to privide a flattened view. Based on documentation context, answer the user question.

    When beeing asked to convert CSN to SQL do the following:
    1) Analyse the CSN structure: 
    - List associations
    - if the CSN contains hierarchies show haw the hierachy associations are linked
    - if the CSN contains filter conditions list them
    - if the CSN contains language dependen text, ask if language filter should be added
    - if the CSN contains validity end dates, ask if filter should be applied for validity end dates
    - if the CSN defines a fact view, then list the fact / transactional data and list the associoated dimensions. include the formulas for calculations/measures.
    - List access control related information
    - Identify the Analytics.dataCategory, explain its meaning and how it affects the SQL transformation
    
    2) create a SQL statement to flatten the CSN structure
    - if the CSN includes hierarchies, exclude them from the SQL, but ask if the hierarchies should be included
    
    Use Databricks SQL, display full SQL query not just a snippet

    ### CSN file:
    {invoiceDetails}
    
    ### Policy Document Context:
    {context}

    ### User Question:
    {question}

    ### Chat History:
    {chatHistory}

    Rules:
    - Answer question directly and concised
    - Using Chat history, allow user to ask follow up questions.
    - If source is from CSN file uploaded, say its CSN file uploaded
    - Include the **source** for each documentation rule you refer to. 
    - Source can be derived from metadata of the page_content where documentation is found. If unknown, write 'Unknown'.
    """
    retriever = db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": 5,
            "score_threshold": 0.3,
            "filter": {}
        }
    )
    class ChatState(TypedDict):
        question: str
        context: List[Document]
        answer: str
        chat_history: List
        invoiceDetails: str

    # Retrieval step
    def retrieve(state: ChatState):
        question = state["question"]
        docs = retriever.get_relevant_documents(question)
        docs = db.similarity_search("", 100)
        return {"context": docs}
    
    # Generation step with memory
    async def generate(state: ChatState):
        question = state["question"]
        context = "\n\n".join(
            f"({doc.metadata.get('source', 'Unknown')})\n{doc.page_content}"
            for doc in state["context"]
        )
        invoice_details = state.get("invoiceDetails", "")

        chat_history = state.get("chat_history", [])
        prompt = prompt_template.format(
            question=question,
            invoiceDetails=invoice_details,
            context=context,
            chatHistory=chat_history
        )

        async for chunk in llm.astream(prompt):
            if chunk.content:
                yield chunk.content

    return {
        "retrieve": retrieve,
        "generate_stream": generate
    }

    # Build the LangGraph
    graph_builder = StateGraph(ChatState).add_sequence([retrieve, generate])
    graph_builder.add_edge(START, "retrieve")
    graph_builder.add_edge("retrieve", "generate")
    graph = graph_builder.compile()

    return graph

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
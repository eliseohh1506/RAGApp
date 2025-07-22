import pandas as pd
import os
from langchain_community.document_loaders import TextLoader
import tempfile
from hdbcli import dbapi
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.docstore.document import Document
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langgraph.graph import START, StateGraph
from typing_extensions import List, TypedDict
import re
from dotenv import load_dotenv
from langchain.schema import Document
import pdfplumber
from PIL import Image
import pytesseract

load_dotenv()

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
        chunk_size=800,
        chunk_overlap=100,
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
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)

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
def get_llm_chain(llm, db):

    # set the prompt templte
    prompt_template = """
    You are an Event Inquiry Chatbot. Based on the user question, answer based on the event context. Show excitement!

    ### Event Document Context:
    {context}

    ### User Question:
    {question}

    Rules:
    - You MUST extract every event listed, including:
        - Events with full descriptions and speakers
        - Events with only a title and time
        - Events labeled as “Break”, “Spotlight”, “Closing Address”, “Showcase Experience”, or similar
    - For each event, list:
        - Title (required)
        - Time (required)
        - Description (optional)
        - Speakers (optional)

    - Do NOT group or summarize multiple events.
    - Pay extra attention to the time for each event! Its there!!
    - List each as a separate bullet or numbered item.
    - If any event lacks a description or speaker, still include it with a note like: "No description provided".
    - Invite users to reprompt if there are key missing information.
    """

    retriever = db.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": 30,
            "score_threshold": 0.3
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
        if not docs:
            docs = db.similarity_search("", 100)
        return {"context": docs}
    
    # Generation step with memory
    def generate(state: ChatState):
        question = state["question"]
        docs = state["context"]

        # Deduplicate by content or content+metadata
        seen = set()
        unique_docs = []
        for doc in docs:
            content_key = (doc.page_content.strip(), doc.metadata.get("page"))
            if content_key not in seen:
                seen.add(content_key)
                unique_docs.append(doc)

        context = "\n\n".join(
            f"(Page {doc.metadata.get('page', 'Unknown')}, Document {doc.metadata.get('title', "Unknown")})\n{doc.page_content}"
            for doc in unique_docs
        )

        chat_history = state.get("chat_history", [])
        prompt = prompt_template.format(
            question=question,
            context=context
        )

        response = llm.invoke(prompt)

        # chat_history.append(HumanMessage(content=question))
        # chat_history.append(AIMessage(content=response.content))

        return {
            "answer": response.content,
            "chat_history": chat_history
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
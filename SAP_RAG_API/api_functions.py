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
from langchain_text_splitters import CharacterTextSplitter
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
            user=os.environ.get("Username"),
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

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text or text.strip() == "":
                # OCR fallback if no text found
                image = page.to_image(resolution=300).original
                text = pytesseract.image_to_string(image)

            texts.append(Document(page_content=text, metadata={"page": i + 1, "source": file_path}))

    return texts

#function to process csv, convert it as docs and return pages
def get_text_from_csv(file, key_column):
    df = pd.read_csv(file)
    loader = DataFrameLoader(data_frame=df, page_content_column=key_column)
    pages = loader.load()
    return pages

#function to process txt, convert it as docs and return pages
def get_text_from_txt(file):
    text_documents = TextLoader(file).load()
    text_splitter = CharacterTextSplitter(chunk_size=250, chunk_overlap=20)
    text_chunks = text_splitter.split_documents(text_documents)
    return text_chunks

#function to create llm-chain and return it
def get_llm_chain(llm, db, file_name):

    # set the prompt templte
    prompt_template = """Use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer. Keep the answer as concise as possible. Always say "thanks for asking!" at the end of the answer. Give the answer in the form of markdown.
    Context: {context}
    Question: {question}
    """
    PROMPT = PromptTemplate(
        template=prompt_template, input_variables=["context", "question"]
    )

    # create memory and llm-chain
    memory = ConversationBufferMemory(
        memory_key="chat_history", output_key="answer", return_messages=True
    )
    qa_chain = ConversationalRetrievalChain.from_llm(
        llm,
        db.as_retriever(search_type="similarity_score_threshold",
            search_kwargs={"k": 5,
                            'score_threshold': 0.3,
                            "filter":{"source":{"$like": "%"+file_name+"%"}}}),
        return_source_documents=True,
        memory=memory,
        verbose=False,
        combine_docs_chain_kwargs={"prompt": PROMPT},
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
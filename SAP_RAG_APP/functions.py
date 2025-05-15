import requests
from requests.auth import HTTPBasicAuth
from hdbcli import dbapi
import pandas as pd
import json
import os
import mimetypes
from IPython.display import display
from dotenv import load_dotenv
load_dotenv()
#function to get the file content
def read_file(filepath):
    with open(filepath, 'r') as file:
        return file.read()

#function to call the file upload api
def call_file_api(input_data):
    files = {"file": input_data}
    api_url = "http://127.0.0.1:8000/upload/"
    response = requests.post(api_url, files=files)
    # Check if the response is successful (200 OK)
    if response.status_code == 200:
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            print("Error: Response is not a valid JSON.")
            return None
    else:
        print(f"Error: Received status code {response.status_code}")
        return None

#function to upload file to dox api
def dox_upload_file(file, document_type, schema_name):
    url = os.environ.get("DOXURL") + "document/jobs"
    accessToken = os.environ.get("DOX_ACCESS_TOKEN")

    mime_type, _ = mimetypes.guess_type(file.name)
    if mime_type is None:
        mime_type = 'application/octet-stream'

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {accessToken}"
    }
    files = {
        'file': (file.name, file, mime_type), 
        'options': (
            None,
            json.dumps({
                "schemaName": schema_name,
                "clientId": os.environ.get("DOX_CLIENT_NAME"),
                "documentType": document_type,
            }),
            'application/json'
        )
    }
    response = requests.post(
        url,
        headers=headers,
        files=files
    )
    if response.status_code == 201:
        results = response.json()
        return results
    else:
        raise Exception(f"Failed to upload file to DOX: {response.status_code} - {response.text}")

#function to call the chat api
def call_chat_api(query, file_name = None, invoiceDetails = None, history = None):
    if file_name == None:
        querys = {"query": query}
    else:
        querys = {"query": query, "file_name": file_name, 
                  "invoiceDetails": json.dumps(invoiceDetails) if invoiceDetails else "{}"}
    api_url = "http://127.0.0.1:8000/chat/"
    resp = requests.post(api_url, data=querys)
    # print(resp.status_code, resp.text)
    response = resp.json()  # only if status and content look correct

    return response

#function to get the hana db connection
def get_hana_db_conn():
    conn = dbapi.connect(
            address=os.environ.get("Hostname"),
            port=os.environ.get("Port"),
            user=os.environ.get("HANA_USERNAME"),
            password=os.environ.get("Password"),
    )
    return conn

#function to get data from table
def get_table_from_cursor(cursor):
        data = pd.DataFrame(cursor.fetchall())
        header = [i[0] for i in cursor.description]
        data = data.rename(columns=dict(zip(data.columns, header)))
        data = data.convert_dtypes()
        return data

#function to get table list from db connection
def get_sap_table(table_name, schema, conn):
    cursor = conn.cursor()
    cursor.execute(f"SELECT VEC_META FROM "+ schema +"." + table_name)
    # cursor.execute(f'''SELECT "VEC_TEXT", "VEC_META", TO_NVARCHAR("VEC_VECTOR") FROM "{table_name}"''')
    # record_columns = cursor.fetchall()
    # for i in range(len(record_columns)):
    #     display(record_columns[i])
    return get_table_from_cursor(cursor)


#function to get the answer from the response
def get_source(response):
    ans = response['answer']
    source = ""
    try:
        if os.path.basename(response['source_documents'][0]['metadata']['source']) != "":
            src = os.path.basename(response['source_documents'][0]['metadata']['source'])
            source += "\n Document Name: " +src + "  Page No.: " + str(response['source_documents'][0]['metadata']['page']+1) 
        
            reply = ans + '\n\n' + 'Source: ' +  source
            return reply
    except:
        return "Sorry There is no relevent Source Document!" + '\n\n' + "Thanks for asking!"
    

#function to call clear data api
def delete_table(filter):
    api_url = "http://127.0.0.1:8000/clear_data/"
    if filter == None:
        response = requests.post(api_url)
    else:
        filter = {"filter": filter}
        response = requests.post(api_url, filter)
    return response

#function to connect to DoX API 
def connect_dox_api():
    auth_url = os.environ.get("DOX_AUTH_URL")
    client_id = os.environ.get("DOX_CLIENT_ID")
    client_secret = os.environ.get("DOX_CLIENT_SECRET")

    if not all([auth_url, client_id, client_secret]):
        raise ValueError("Missing required environment variables for DoX API authentication.")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    params = {
        "grant_type": "client_credentials",
        "response_type": "token"
    }

    response = requests.post(
        auth_url,
        headers=headers,
        params=params,
        auth=HTTPBasicAuth(client_id, client_secret)
    )

    if response.status_code == 200:
        access_token = response.json().get("access_token")
        os.environ["DOX_ACCESS_TOKEN"] = access_token
        return access_token
    else:
        raise Exception(f"Failed to get access token: {response.status_code} - {response.text}")

# get all documents in DoX
def dox_get_all_documents():   
    clientID = os.environ.get("DOX_CLIENT_NAME")
    url = os.environ.get("DOXURL") + "document/jobs" + f"?clientId={clientID}"
    if not (clientID):
        url =  os.environ.get("DOXURL") + "document/jobs"

    accessToken = os.environ.get("DOX_ACCESS_TOKEN")
    headers = {
        "accept": "application/x-www-form-urlencoded",
        "Authorization": f"Bearer {accessToken}"
    }

    response = requests.get(
        url,
        headers=headers
    )

    if response.status_code == 200:
        results = response.json().get("results")
        return results
    else:
        raise Exception(f"Failed to get DOX Documents: {response.status_code} - {response.text}")

# function to get the fields of a DOX document
def dox_get_fields(name):
    results = dox_get_all_documents()
    id = ""
    for result in results:
        if result.get("fileName") == name:
            id = result.get("id")
            break 

    if not (id):
        raise Exception(f"Cannot match document name to document ID")
    else: 
        url = os.environ.get("DOXURL") + "document/jobs" + f"/{id}"
        accessToken = os.environ.get("DOX_ACCESS_TOKEN")
        headers = {
            "accept": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {accessToken}"
        }

        response = requests.get(
            url,
            headers=headers
        )

        if response.status_code == 200:
            results = response.json().get("extraction")
            return results
        else:
            raise Exception(f"Failed to get DOX Documents: {response.status_code} - {response.text}")
        
# function to get the id of a DOX document
def dox_getId(name):
    results = dox_get_all_documents()
    id = ""
    for result in results:
        if result.get("fileName") == name:
            id = result.get("id")
            return id

    if not (id):
        raise Exception(f"Cannot match document name to document ID")
        
def dox_get_schemas():
    clientID = os.environ.get("DOX_CLIENT_NAME")
    url = os.environ.get("DOXURL") + "schemas" + f"?clientId={clientID}"
    accessToken = os.environ.get("DOX_ACCESS_TOKEN")
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {accessToken}"
    }
    response = requests.get(
        url,
        headers=headers
    )
    if response.status_code == 200:
        results = response.json().get("schemas")
        active_schemas = [schema for schema in results if schema.get("state") == "active"]
        return active_schemas
    else:
        raise Exception(f"Failed to get DOX Documents: {response.status_code} - {response.text}")

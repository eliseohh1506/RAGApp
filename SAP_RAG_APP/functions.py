import requests
from hdbcli import dbapi
import pandas as pd
import os


#function to get the file content
def read_file(filepath):
    with open(filepath, 'r') as file:
        return file.read()

#function to call the file upload api
def call_file_api(input_data):
    files = {"file": input_data}
    api_url = "http://127.0.0.1:8000/upload/"
    api_geturl = "http://127.0.0.1:8000/embedding-dim/"
    response = requests.post(api_url, files=files)
    response2 = requests.get(api_geturl)
    if response2.status_code == 200:
        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            print("Error: Response is not a valid JSON.")
            return None
    else:
        print(f"Error: Received status code {response2.status_code}")
        return None
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

#function to call the chat api
def call_chat_api(query, file_name = None, history = None):
    if file_name == None:
        querys = {"query": query}
    else:
        querys = {"query": query, "file_name": file_name}
    api_url = "http://127.0.0.1:8000/chat/"
    response = requests.post(api_url, querys).json()
    return response

#function to get the hana db connection
def get_hana_db_conn():
    conn = dbapi.connect(
            address=os.environ.get("Hostname"),
            port=os.environ.get("Port"),
            user=os.environ.get("Username"),
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
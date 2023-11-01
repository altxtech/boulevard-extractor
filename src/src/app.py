from flask import Flask, Request
from extract import create_gql_client, load_query
from google.cloud import storage

GQL_CLIENT = None
def get_gql_client():
    global GQL_CLIENT
    if GQL_CLIENT == None:
        GQL_CLIENT = create_gql_client()
    return GQL_CLIENT

STORAGE_CLIENT = None 
def get_storage_client():
    global STORAGE_CLIENT
    if STORAGE_CLIENT == None:
        STORAGE_CLIENT = storage.Client()
    return STORAGE_CLIENT

def extractionasdf

app = Flask(__name__)

'''
There's some temptation here to use an edpoint name like "extract_orders"

However, I want to try my best to abide to REST conventions, which state that
endpoint names should be nouns, not verbs.  

Therefore, I'm using the notion of an "extraction job" entity. When you make a POST
request to this endpoint, you create an extraction job
'''


@app.route('/job', methods = ['POST'])
def create_job():
    pass

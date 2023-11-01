import os
import json
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from time import time
from datetime import datetime, timedelta
from base64 import b64decode, b64encode
import hmac
from hashlib import sha256
import logging
from sys import argv
import traceback
from google.cloud import storage
import asyncio
from time import sleep, time
from dotenv import load_dotenv
import backoff
from copy import copy
from async_writers.gcs_async_writer import GCSAsyncWriter
load_dotenv()

ENV='prod'

# List of possible extractable entities
# General entities that do not depend on location
GEN_ENTITIES = ['staff']
# Location based entities, that can only be queried by location 
LOC_ENTITIES = []

# GQL AUTH
def generate_http_creds(business_id, api_secret, api_key):
    prefix = 'blvd-admin-v1'
    timestamp = str(int(time()))

    payload_str = prefix + business_id + timestamp
    payload = payload_str.encode('utf-8')
    raw_key = b64decode(api_secret)
    signature = hmac.new(raw_key, payload, sha256).digest()
    signature_base64 = b64encode(signature).decode('utf-8')
    token = f'{signature_base64}{payload.decode("utf-8")}'
    http_basic_payload = f'{api_key}:{token}'
    http_basic_credentials = b64encode(http_basic_payload.encode('utf-8')).decode('utf-8')

    return http_basic_credentials

def create_gql_client():
    token = generate_http_creds(
            os.environ['BOULEVARD_BUSINESS_ID'],
            os.environ['BOULEVARD_API_SECRET'],
            os.environ['BOULEVARD_API_KEY']
    )
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {token}'
    }
    transport = AIOHTTPTransport(url=os.environ["BOULEVARD_URL"], headers=headers)
    client = Client(transport=transport, fetch_schema_from_transport=False)
    return client

# HELPER FUNCTIONS
def load_query(query_file):

    with open(f"src/graphql/{query_file}.graphql") as file:
        query_text = file.read()
    
    query = gql(query_text)
    return query


# TASK LOGIC
def create_task(part: str, cursor: str, entity_name: str, query_params: dict):
    return { 
        'status': 'CREATED',
            'args': {
                'part': part,
                'cursor': cursor,
                'entity_name': entity_name,
                'query_params': query_params
            }
    }

async def add_task_to_queue(task, queue, tasks):
    tasks.append(task)
    await queue.put(tasks[-1])
    

async def consume_task_queue(queue, tasks, bucket_name):
    print("This print never appears")
    # Create gql and bigquery clients
    gcs_writers = {}

    # Create a list to store the task execution coroutines
    while True:
        # Create a GQL client
        print('Refreshing GraphQL client connection')
        client = create_gql_client()
        
        # Watch for the client_timer
        async with client as session:
            session_timer = time()
            while time() - session_timer < 300: # Refresh the connection every 5 minutes
                # Get task from queue
                task = await queue.get()

                # Get the proper GCS Writer for this partition
                part = task['args']['part']
                gcs_writer = gcs_writers.get(part) 
                if gcs_writer == None:
                    # Create writer if necessary
                    gcs_writer = GCSAsyncWriter(bucket_name, part)
                    gcs_writers[part] = gcs_writer

                # Run task 
                asyncio.create_task(
                    execute_task(session, task, queue, tasks, gcs_writer) # Task executiom may add more tasks to the queue
                )

                # Backoff - Give time to other stuff execution + respect rate limit
                await asyncio.sleep(1.2)


async def execute_task(session, task, queue, tasks, writer):
    print(f"Processing task: {task['args']['part']}{task['args']['cursor']}")
    # Check if task is done
    if task['status'] == 'SUCCESS':
        print('Task already completed.')
        queue.task_done()
        return

    try:
        # Step 1 - Load the query
        entity_name = task['args']['entity_name']
        query = load_query('list_' + entity_name)
        # Step 2 - Execute the query
        params = task['args']['query_params']
        results = await exponential_backoff_execute(session, query, params) # Here we want to await, because we can't do step 3 without the results
        cursor = results[entity_name]['edges'][0]['cursor'] # Hash to use to define the page names 

        # Step 3 - Save results to GCS
        rows = [{'loaded_at': datetime.utcnow().isoformat(), 'node': edge['node']} for edge in results[entity_name]['edges']]
        write_task = asyncio.create_task(writer.write_rows(rows, cursor))

        # Step 4 - Check if there is a next page, if, so, add a new tasks the queue
        if results[entity_name]['pageInfo']['hasNextPage']:
            # Create a new task
            new_params = copy(params)
            new_params['after'] = results[entity_name]['pageInfo']['endCursor']
            new_task = create_task(task['args']['part'], results[entity_name]['pageInfo']['endCursor'], entity_name, new_params)
            await add_task_to_queue(new_task, queue, tasks) # Here we await, because there isn't anything else to do

        # Check for errors on write
        write_result = await write_task
        if isinstance(write_result, Exception):
            raise write_result
            
        task['status'] = 'SUCCESS'
        return True
        
    except Exception as e:
        error_message = traceback.format_exc()
        print(error_message)
        task['status'] = 'FAILED'
        task['error'] = str(error_message)
        return False

    queue.task_done()


@backoff.on_exception(backoff.expo, Exception, max_time=120)
async def exponential_backoff_execute(session, query, params):
    return await session.execute(query, variable_values = params)


# INITAL SETUP
async def create_initial_tasks(bucket_name, prefix: str = ''):
    '''
    Create all tasks except for the locations task
    The task to extract the locations should be executed before running this function
    '''
    tasks = []

    # Create tasks for general entities
    for entity in GEN_ENTITIES:
        part_name = entity + '/'
        tasks.append(
                create_task(part_name, 'first', entity, {'after': None, 'first': 100})
        )

    # Create location based tasks
    # Load locations
    bucket = storage.Client().bucket(bucket_name)
    locations_jsonl = await load_from_gcs(bucket, prefix + 'locations/YXJyYXljb25uZWN0aW9uOjA=.json')
    locations = [json.loads(line) for line in locations_jsonl.splitlines()]

    for entity in LOC_ENTITIES:
        for loc in locations:
            part_name = f"{entity}/{loc['node']['id']}/"
            tasks.append(
                    create_task(part_name, 'first', entity, {'after': None, 'first': 100, 'locationId': loc['node']['id'], 'query': "createdAt >= '2023-09-26' OR updatedAt >= '2023-09-26' OR closedAt >= '2023-09-26'"})
            )
    return tasks


async def load_from_gcs(bucket, name):
    # Create a new client every time this method is called, 
    blob = bucket.blob(name)
    if blob.exists():
        return blob.download_as_text()
    return None

async def save_to_gcs(bucket, obj, name):
    blob = bucket.blob(name)
    blob.upload_from_string(json.dumps(obj), 'application/json')

# MAIN
async def run_boulevard_historical_data_extraction(bucket_name: str, prefix: str = ''): 

    tmp_tasks = []
    q = asyncio.Queue()
    tmp_client = create_gql_client()
    locations_writer = GCSAsyncWriter(bucket_name, prefix + "locations/")
    
    # Execute locations task
    print('Extracting locations...')
    loc_task = create_task('locations', None, 'locations', {'after':None, 'first':100})
    async with tmp_client as session:
        await execute_task(session, loc_task, q, tmp_tasks, locations_writer)
    del tmp_client
    del tmp_tasks
    del locations_writer

    # Create tasks, if they don't exist
    print('Evaluating tasks...')
    tasks_bucket = storage.Client().bucket(bucket_name)
    tasks_json = await load_from_gcs(tasks_bucket, 'tasks.json') # This is a string
    if tasks_json is None:
        print('Task file does not exist in GCS. Creating.')
        tasks = await create_initial_tasks(bucket_name, prefix)
        await save_to_gcs(tasks_bucket, tasks, 'tasks.json')
    else:
        print('Tasks file already exists in GCS. Skipping step')
        tasks = json.loads(tasks_json)

    # Cleanup tasks
    print("Cleaning up stale tasks...")
    tasks = [task for task in tasks if task['status'] != 'SUCCESS']
    print(tasks)

    # Add tasks to the queue
    print("Queuing tasks")
    for t in tasks:
        await q.put(t)

    # Process all tasks concurrently
    print("Processig tasks")
    asyncio.create_task(consume_task_queue(q, tasks, bucket_name))

    # Save the task file continously
    print("This print never appears")
    while True:
        await asyncio.sleep(60) # Every minute
        await save_to_gcs(tasks_bucket, tasks, 'tasks.json')
        if q.qsize() == 0:
            break
    await q.join()
    await save_to_gcs(tasks_bucket, tasks, 'tasks.json')

if __name__ == "__main__":
    bucket = os.environ['BOULEVARD_HISTORICAL_DATA_BUCKET_NAME'] # This is a global varial LMAO
    asyncio.run(run_boulevard_historical_data_extraction(bucket))

import asyncio
from os import sendfile
from google.cloud import storage
import backoff
import json
from typing import Optional
import asyncio
from hashlib import md5

# Each async writer should write to a different table
class GCSAsyncWriter:
    def __init__(self, bucket_name: str, prefix: str = ''):
        self.client = storage.Client() # I'm going to assume it doesn't need ot be refreshed for now
        self.bucket = self.client.get_bucket(bucket_name)
        self.path = prefix

    async def write_rows(self, rows: list[dict], page: str = None) -> Optional[Exception]:
        try:
            row_lines = self._make_jsonl(rows)
            filename = self._define_filename(page)
            await self._save_to_gcs(row_lines, filename)
            return None
        except Exception as e:
            return e
    
    def _make_jsonl(self, rows: list[dict]) -> str:
        # TODO: Implement
        row_lines = [json.dumps(row) for row in rows]
        return '\n'.join(row_lines)

    def _define_filename(self, page):
        # For now, name is prefix + page
        if page == None:
            page = md5(page.encode('utf-8')).hexdigest()
        return self.path + page + '.json' 

    @backoff.on_exception(backoff.expo, Exception, max_time=300)
    async def _save_to_gcs(self, content: str, filename: str):
        # Save locally. Will be changed to gcp cloud storage later
        blob = self.bucket.blob(filename)
        coro = asyncio.to_thread(blob.upload_from_string, content, content_type='application/json')
        asyncio.create_task(coro)

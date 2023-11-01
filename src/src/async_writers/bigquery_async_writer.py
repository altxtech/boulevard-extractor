import asyncio
import pandas as pd
import pandas_gbq
import backoff
from time import perf_counter, sleep

'''
The BigQueryAsyncWriter is not being used right. Didn't throw it away
because I may want to fix and use it in the future. But I think it can be massivelly simplified
'''

class BigQueryAsyncWriter:
    def __init__(self, project_id, dataset_id):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.write_queue = asyncio.Queue()
        self.worker_task = asyncio.create_task(self._worker())
        self.task_counter = {}

    async def _worker(self):
        while True:
            table_name, rows = await self.write_queue.get()
            if table_name is None:  # Signal to stop the worker
                self.write_queue.task_done()
                break

            # Define the name of the task_done
            if self.task_counter.get(table_name) == None:
                self.task_counter[table_name] = -1
            self.task_counter[table_name] += 1
            task_num = self.task_counter[table_name]
            task_name = f"{table_name}-{task_num}"

            coro = asyncio.to_thread(self._write_to_bigquery, table_name, rows)
            asyncio.create_task(coro, name = task_name)

    @backoff.on_exception(backoff.expo, Exception, max_time=120)
    def _write_to_bigquery(self, table_name, rows):
        df = pd.DataFrame.from_dict(rows)
        full_table_name = f"{self.project_id}.{self.dataset_id}.{table_name}"
        pandas_gbq.to_gbq(df, full_table_name, project_id=self.project_id, if_exists='append')
        self.write_queue.task_done()

    async def write_rows(self, table_name, rows):
        await self.write_queue.put((table_name, rows))

    async def close(self):
        await self.write_queue.put((None, None))
        await self.write_queue.join()

# Usage
async def main():
    writer = BigQueryAsyncWriter("even-affinity-388602", "dw_dev_staging_blvd_historical")

    write_request = ("person", [{'name': 'André', 'id': 337 }])

    for i in range(2):
        print(f"Performing loop {i}")
        t = perf_counter()
        for _ in range(2):
            await writer.write_rows(write_request[0], write_request[1])
        e = perf_counter() - t
        print(f"Loop {i} took {e:.2f} secods")

    print('Closing writer')
    await writer.close()  # Close the writer when done

if __name__ == "__main__":
    asyncio.run(main())

